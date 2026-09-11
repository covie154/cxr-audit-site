# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Admin-only YAML layout editor: a thin, security-gated UI over the verified backends.

This module adds *no* new persistence, validation or evaluation logic. Every durable move is
delegated to :class:`report_v2.definitions.repository.DefinitionRepository` (Task 11), and every
validation/rendering answer comes from the strict loader (Task 03), the display validators
(Task 09) and :func:`report_v2.evaluation.evaluate` (Task 10).

Security posture (the point of Task 12):

* **Every** view -- including the page itself -- first passes :func:`require_admin`, which reuses the
  one house edit predicate (``admins`` group or superuser) from :mod:`report_v2.permissions`. An
  anonymous visitor is redirected to the login page and an authenticated non-admin gets ``403``,
  *before* any model or filesystem work happens. That holds for a hand-crafted ``POST`` straight to
  a mutation URL too: the gate is the first statement inside the view, not a template nicety.
* Every mutating view additionally carries ``@require_POST`` plus ``csrf_protect``, so a
  cross-site form post (no token) is rejected by ``CsrfViewMiddleware`` before the view body runs.
* ``editor_publish`` is the **only** code path that may move a publication pointer, and only on an
  explicit user action. ``editor_preview`` never publishes and never sends mail; a rejected publish
  leaves the old pointer exactly where it was (Task 11's guarantee, relied upon, never bypassed).
* There is no pointer-reordering editing surface: the editor is a plain ``<textarea>`` plus buttons.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from django.conf import settings as django_settings
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from . import permissions
from .definitions.repository import (
    DefinitionRepository,
    DraftNotFoundError,
    PublishRejectedError,
    RepositoryError,
    StaleRevisionError,
    default_root,
)
from .evaluation import (
    PUBLISHED_WIDGETS,
    EvaluationError,
    RequestContract,
    evaluate,
)
from .projects.prime import get_project_definition

__all__ = [
    "editor",
    "editor_new",
    "editor_preview",
    "editor_publish",
    "editor_save_draft",
]

#: The editor edits the definitions of the single production project (Task 04).
PROJECT_ID = "prime"

#: Starter scaffold handed to a brand-new report so the first draft is a valid, empty layout.
STARTER_YAML = """\
schema_version: 1
project: prime
id: {def_id}
title: New report
grid:
  columns: 12
  row_height_px: 64
sections: []
"""


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def _param(request, name: str, default: Any = "") -> Any:
    """Read one body parameter from a form-encoded or JSON request body.

    Missing keys yield *default*; the CSRF field is never echoed back. The body is only decoded
    for ``application/json`` requests, so a form post never has to be parsed twice.
    """
    value = request.POST.get(name, None)
    if value is None:
        content_type = request.META.get("CONTENT_TYPE", "") or ""
        if "application/json" in content_type:
            try:
                payload = json.loads(request.body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                payload = {}
            if isinstance(payload, dict):
                value = payload.get(name, default)
    return default if value is None else value


def _expected_revision(request) -> str | None:
    """The caller's optimistic-concurrency token; an empty value means 'no assertion'."""
    raw = _param(request, "expected_revision", None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _user_of(request):
    """The acting user, defaulting to the anonymous one when no middleware supplied it."""
    user = getattr(request, "user", None)
    if user is None:
        return AnonymousUser()
    return user


def _login_redirect(request) -> HttpResponseRedirect:
    """Mirror the house ``user_passes_test`` behaviour: send anonymous users to the login page."""
    login_url = str(getattr(django_settings, "LOGIN_URL", "login") or "login")
    next_path = getattr(request, "get_full_path", lambda: request.path)()
    return HttpResponseRedirect(f"/{login_url.strip('/')}/?next={quote(next_path, safe='/?=&')}")


def _admin_gate(request):
    """Return a denial response, or ``None`` when the request may proceed.

    The predicate is the *shared* house one (``report_v2.permissions.can_edit_catalog`` ->
    ``_is_admin``): superuser or member of the ``admins`` group. Nothing here invents a second
    authorisation scheme, and nothing touches the filesystem or the models before this returns.
    """
    user = _user_of(request)
    if not getattr(user, "is_authenticated", False):
        return _login_redirect(request)
    if not permissions.can_edit_catalog(user):
        return HttpResponseForbidden("admin only")
    return None


def require_admin(view_func):
    """Gate a view behind the shared admin predicate *before* any other work is done.

    The wrapper deliberately does not copy ``require_POST``/``csrf_protect`` markers off the inner
    view: ``functools.wraps`` would otherwise publish the mutation views' ``require_POST`` restriction
    onto the admin wrapper and reject the very ``POST`` the view exists to serve. The attributes are
    therefore set from the *wrapper's* own needs, and ``csrf_exempt`` stays absent/false so the CSRF
    middleware keeps protecting every mutating endpoint.
    """

    def _wrapped(request, *args, **kwargs):
        denied = _admin_gate(request)
        if denied is not None:
            return denied
        return view_func(request, *args, **kwargs)

    _wrapped.__name__ = getattr(view_func, "__name__", "view")
    _wrapped.__doc__ = view_func.__doc__
    _wrapped.__wrapped__ = view_func
    return _wrapped


def _repository() -> DefinitionRepository:
    """One repository per request, rooted at the configured (never public) publish root.

    ``default_root()`` is consulted per call so an operator -- or a test -- can relocate the whole
    editor by pointing ``settings.REPORT_V2_ROOT`` at a scratch directory; nothing is ever written
    under ``STATIC_ROOT``/``MEDIA_ROOT``.
    """
    return DefinitionRepository(default_root(), project_id=PROJECT_ID)


def _draft_ids(repo: DefinitionRepository) -> list[str]:
    """The def_ids that currently have a draft, read from the private drafts directory."""
    drafts = Path(repo._drafts_dir)
    if not drafts.exists():
        return []
    return sorted(p.name for p in drafts.iterdir() if p.is_file())


def _first_supported_widget() -> str | None:
    """The first published widget id the evaluator accepts (deterministic insertion order)."""
    for widget_id in PUBLISHED_WIDGETS:
        return widget_id
    return None


# ---------------------------------------------------------------------------
# The editor page (read-only)
# ---------------------------------------------------------------------------
@require_GET
@require_admin
def editor(request, def_id: str | None = None):
    """Render the YAML layout editor (admins only; no draft is written on this path)."""
    repo = _repository()
    draft_text = ""
    revision = ""
    if def_id:
        try:
            draft_text, revision = repo.read_draft(def_id)
        except (DraftNotFoundError, RepositoryError):
            draft_text, revision = "", ""
    return render(
        request,
        "report_v2/layout.html",
        {
            "def_id": def_id or "",
            "draft_text": draft_text,
            "revision": revision,
            "reports": _draft_ids(repo),
            "project_id": PROJECT_ID,
        },
    )


# ---------------------------------------------------------------------------
# Mutating endpoints (admin + POST + CSRF, all three)
# ---------------------------------------------------------------------------
@require_POST
@csrf_protect
@require_admin
def editor_save_draft(request):
    """Persist a draft only. Never validates, never publishes, never mails."""
    def_id = str(_param(request, "def_id", "")).strip()
    yaml_text = str(_param(request, "yaml_text", ""))
    if not def_id:
        return JsonResponse({"error": "def_id is required"}, status=400)
    repo = _repository()
    try:
        revision = repo.save_draft(def_id, yaml_text, expected_revision=_expected_revision(request))
    except (StaleRevisionError,):
        # Optimistic concurrency: the caller's token is out of date. The stored draft is left
        # exactly as it is (no clobber) and the client is told to reload.
        return JsonResponse(
            {"error": "version conflict: reload", "def_id": def_id, "status": "conflict"},
            status=409,
        )
    except (RepositoryError,) as exc:
        return JsonResponse({"error": str(exc), "def_id": def_id}, status=400)
    return JsonResponse({"def_id": def_id, "revision": revision, "status": "saved"}, status=200)


@require_POST
@csrf_protect
@require_admin
def editor_preview(request):
    """Validate and render a preview. Read-only by contract: no draft, no publish, no mail.

    ``repo.validate_preview`` (loader 03 + display validators 09) produces the typed error list;
    only when that list is empty do we ask :func:`report_v2.evaluation.evaluate` for the data of
    the *first supported widget* so the normal renderer can paint something. An evaluation failure
    is reported as preview information -- it can never turn into a publication.
    """
    def_id = str(_param(request, "def_id", "")).strip()
    yaml_text = str(_param(request, "yaml_text", ""))
    repo = _repository()
    probe_id = def_id or "__preview__"
    errors = repo.validate_preview(probe_id, yaml_text)
    payload: dict[str, Any] = {"def_id": def_id, "errors": errors, "valid": not errors, "preview": None}
    if errors:
        return JsonResponse(payload, status=200)
    widget_id = _first_supported_widget()
    if widget_id is None:
        payload["preview_error"] = "no published widget is available"
        return JsonResponse(payload, status=200)
    try:
        result = evaluate(
            request=RequestContract(widget_id=widget_id),
            project=get_project_definition(),
            catalog=None,
            rows=[],  # a preview paints from no clinical rows; the renderer owns the data fetch
            include_rows=False,
        )
    except Exception as exc:  # read-only preview: never let a render error escape into a 500
        # A preview is information only. An empty-population / evaluation failure -- e.g. an
        # EmptyPopulationError raised by the classification layer over an empty synthetic row set --
        # is reported as preview text. It can NEVER turn into a publication: this code path holds no
        # publish call at all, and Task 11's publish is reachable only through editor_publish.
        payload["widget_id"] = widget_id
        payload["preview_error"] = str(exc)
        return JsonResponse(payload, status=200)
    payload["widget_id"] = widget_id
    payload["preview"] = result.to_dict()
    return JsonResponse(payload, status=200)


@require_POST
@csrf_protect
@require_admin
def editor_publish(request):
    """The single publish path, reached only by an explicit Publish button press.

    ``PublishRejectedError`` (invalid YAML / failed display validation) surfaces the validation
    errors and -- because Task 11 validates *before* the pointer flip -- leaves the current pointer
    untouched; that is asserted by ``test_invalid_yaml_does_not_replace_published``.
    """
    def_id = str(_param(request, "def_id", "")).strip()
    yaml_text = str(_param(request, "yaml_text", ""))
    if not def_id:
        return JsonResponse({"error": "def_id is required"}, status=400)
    repo = _repository()
    try:
        receipt = repo.publish(def_id, yaml_text, expected_revision=_expected_revision(request))
    except (PublishRejectedError,) as exc:
        return JsonResponse(
            {"error": "publish rejected", "errors": [str(exc)], "def_id": def_id, "status": "rejected"},
            status=422,
        )
    except (StaleRevisionError,):
        return JsonResponse(
            {"error": "version conflict: reload", "def_id": def_id, "status": "conflict"},
            status=409,
        )
    except (RepositoryError,) as exc:
        return JsonResponse({"error": str(exc), "def_id": def_id}, status=400)
    return JsonResponse(
        {
            "def_id": def_id,
            "version": receipt.version,
            "pointer": repo._read_pointer(def_id),
            "status": "published",
        },
        status=200,
    )


@require_POST
@csrf_protect
@require_admin
def editor_new(request):
    """Create a second, independent report: a fresh ``def_id`` plus a starter scaffold draft."""
    def_id = str(_param(request, "def_id", "")).strip()
    if not def_id:
        return JsonResponse({"error": "def_id is required"}, status=400)
    repo = _repository()
    scaffold = STARTER_YAML.format(def_id=def_id)
    try:
        revision = repo.save_draft(def_id, scaffold, expected_revision=None)
    except (RepositoryError,) as exc:
        return JsonResponse({"error": str(exc), "def_id": def_id}, status=400)
    return JsonResponse(
        {"def_id": def_id, "revision": revision, "yaml_text": scaffold, "status": "created"},
        status=200,
    )
