# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Public, login-gated read surface for *published* report-v2 layouts.

Security posture (the invariant this module is written around):

* Every forged-input gate runs **before** any row is fetched. The single ORM seam
  (:func:`report_v2.data.fetch_project_rows`) is reached only at the very last step of the data
  endpoint, so no 4xx path -- tampered context, rejected override, unknown id, stale version -- can
  touch the database or leak row data in an error body.
* Drafts are never rendered: layouts are loaded only through
  :meth:`report_v2.data.load_published_layout`, which raises :class:`~report_v2.data.PublishedNotFoundError`
  for absent / draft-only / unparseable reports (surface as :class:`~django.urls.Resolver404`, never a
  ``500``).
* The per-widget context token that rides into the browser is **server-signed** (HMAC over the salted
  ``slug|version|widget_id`` tuple) and is re-verified before use. The published *version* a widget was
  rendered under is pinned inside that signature: a client can never change it by editing the request
  body -- the version is only ever read back out of the verified token, so a stale token yields ``409``
  and a forged one yields ``403`` rather than silently re-scoping an evaluation.
* A whole-page render is fault-isolated per widget frame: any error inside one frame is captured into
  that frame's payload as an ``error`` string and the sibling frames still render -- a single bad widget
  can never turn the page into a ``500``.

The index view keeps the exact behaviour and HTML markers the routing tests pin (it renders no
clinical data and touches no database); the two new views add the published report page and its
per-widget JSON data endpoint.
"""
from __future__ import annotations

import json
import re
from typing import Mapping

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, reverse
from django.utils.html import escape
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from . import data
from .definitions.repository import InvalidDefinitionIdError, validate_definition_id
from .evaluation import EvaluationError, RequestContract, WidgetSpec, evaluate
from .permissions import can_edit_catalog
from .projects.prime import get_project_definition

__all__ = ["index", "report_page", "widget_data"]

#: The single production project every published report is scoped to (Task 04).
_PROJECT_ID = "prime"

#: Domain-separated salt for the per-widget context signature (never reused elsewhere).
_CTX_SALT = "report_v2.page_context.v1"

#: Rows a table widget renders/serves per page (well inside the evaluator's hard
#: :data:`~report_v2.evaluation.MAX_PAGE_SIZE` cap) and the last page a client may ask for.
_SERVER_PAGE_SIZE = 50
_MAX_PAGE = 100

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RELATIVE_RE = re.compile(r"^(?:D|W|M|Y)(?:-\d+)?$")
_WINDOW_START_RE = re.compile(r"^(?:D|W|M|Y)(?:-\d+)?$")

#: The only top-level keys a widget-data body may carry. Anything else (version / anchor /
#: measurement(_override) / policy_version_override / ci_override / layout_override / include_rows /
#: rows / widget_id / bucket / ...) is a disallowed override attempt and is rejected up-front.
_ALLOWED_TOP_KEYS = frozenset({"context", "date", "filters", "comparison", "page", "request_seq"})

#: The scalar types an override filter value may be (or a list/tuple of these, bounded in length).
_SCALAR_TYPES = (str, int, float, bool)
_MAX_FILTER_LIST = 50


class TamperedContextError(Exception):
    """The signed per-widget context token failed to verify (forge / expiry / wrong salt / malformed)."""


class OverrideRejectedError(Exception):
    """A request override is outside the per-widget allow-list, or is malformed."""


# ---------------------------------------------------------------------------
# Signed per-widget context token (server-authoritative slug/version/widget binding)
# ---------------------------------------------------------------------------
def _widget_context_token(slug: str, version: str, widget_id: str) -> str:
    """Sign the ``slug|version|widget_id`` tuple the frame was rendered under."""
    return signing.dumps(f"{slug}|{version}|{widget_id}", salt=_CTX_SALT)


def _parse_widget_context(token: object) -> tuple[str, str, str]:
    """Verify ``token`` and split it back into ``(slug, version, widget_id)``.

    Any failure to unsalt-verify -- a bad signature, an expired timeframe, a wrong salt, a
    non-string payload or a malformed split -- is a :class:`TamperedContextError`; the caller turns
    that into a ``403`` *before* anything is read. This is deliberately fail-closed.
    """
    try:
        value = signing.loads(token, salt=_CTX_SALT)
    except Exception as exc:  # BadSignature / SignatureExpired / ValueError / TypeError / ...
        raise TamperedContextError("context token failed to verify") from exc
    if not isinstance(value, str):
        raise TamperedContextError("context token payload is malformed")
    parts = value.split("|")
    if len(parts) != 3:
        raise TamperedContextError("context token payload is malformed")
    return parts[0], parts[1], parts[2]


# ---------------------------------------------------------------------------
# Layout-derived catalog (decision D3): the published widgets *are* the evaluator's allow-list
# ---------------------------------------------------------------------------
def _layout_widgets(layout: dict) -> dict[str, dict]:
    """Map ``widget_id -> widget dict`` walking sections (and widgets) in declared render order."""
    widgets: dict[str, dict] = {}
    for section in layout.get("sections") or []:
        for widget in section.get("widgets") or []:
            widget_id = widget.get("id")
            if widget_id is not None:
                widgets[widget_id] = widget
    return widgets


def _build_specs(layout: dict) -> dict[str, WidgetSpec]:
    """Derive a frozen :class:`~report_v2.evaluation.WidgetSpec` per widget from the *layout*.

    The layout is the published allow-list: a widget's declared ``measurement``/``type`` fix what it
    may compute and ``aggregate`` is ``True`` for everything except a ``table`` (only a non-aggregate
    widget may publish raw case-level rows). ``window`` falls back to ``D-30`` unless the widget's own
    ``window.start`` is already a relative token.
    """
    specs: dict[str, WidgetSpec] = {}
    for widget_id, widget in _layout_widgets(layout).items():
        display = widget.get("type")
        measurement = (widget.get("query") or {}).get("measurement")
        controls = widget.get("controls") or {}
        window_start = (widget.get("window") or {}).get("start") or ""
        window = window_start if _WINDOW_START_RE.match(window_start) else "D-30"
        specs[widget_id] = WidgetSpec(
            widget_id=widget_id,
            display=display,
            measurement=measurement,
            aggregate=(display != "table"),
            paired=measurement in {"agreement_kappa", "agreement_mcnemar", "fn_fp_cases"},
            window=window,
            filters=frozenset(controls.get("filters") or ()),
            dimensions=frozenset(controls.get("compare_by") or ()),
        )
    return specs


def _allowed_controls(widget: dict) -> dict:
    """The client-visible control surface for a widget (a copy of its controls + a few read-only hints)."""
    controls = widget.get("controls") or {}
    query = widget.get("query") or {}
    return {
        "date_range": bool(controls.get("date_range")),
        "filters": list(controls.get("filters") or ()),
        "compare_by": list(controls.get("compare_by") or ()),
        "measurement": query.get("measurement"),
        "inputs": dict(query.get("inputs") or {}),
        "window": dict(widget.get("window") or {}),
        "default_compare_by": widget.get("default_compare_by"),
        "type": widget.get("type"),
    }


# ---------------------------------------------------------------------------
# Override validation -- every gate here runs against the layout only; nothing reads a row
# ---------------------------------------------------------------------------
def _check_top_keys(body: dict) -> None:
    """Reject any top-level key outside the allow-list before it is ever interpreted."""
    for key in body:
        if key not in _ALLOWED_TOP_KEYS:
            raise OverrideRejectedError(f"unexpected top-level key {key!r}")


def _validate_date(raw: object) -> dict | None:
    """Validate a ``date`` override into the shape the evaluator's ``date_override`` expects."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise OverrideRejectedError("date override must be an object")
    if "relative" in raw:
        if set(raw) - {"relative"}:
            raise OverrideRejectedError("relative date override carries unexpected keys")
        token = raw.get("relative")
        if not isinstance(token, str) or not _RELATIVE_RE.match(token):
            raise OverrideRejectedError("relative window token is invalid")
        return {"relative": token}
    start = raw.get("start")
    end = raw.get("end")
    if not isinstance(start, str) or not _ISO_RE.match(start):
        raise OverrideRejectedError("date start must be a YYYY-MM-DD date")
    if not (end == "D" or (isinstance(end, str) and _ISO_RE.match(end))):
        raise OverrideRejectedError("date end must be a YYYY-MM-DD date or 'D'")
    return {"start": start, "end": end}


def _validate_filters(widget: dict, raw: object) -> dict:
    """Validate a ``filters`` override against the widget's declared filter allow-list."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise OverrideRejectedError("filters override must be an object")
    allowed = frozenset((widget.get("controls") or {}).get("filters") or ())
    out: dict = {}
    for key, value in raw.items():
        if key not in allowed:
            raise OverrideRejectedError(f"filter {key!r} is not permitted on this widget")
        if isinstance(value, _SCALAR_TYPES):
            out[key] = value
        elif isinstance(value, (list, tuple)):
            if len(value) > _MAX_FILTER_LIST:
                raise OverrideRejectedError(f"filter {key!r} has too many values")
            for item in value:
                if not isinstance(item, _SCALAR_TYPES):
                    raise OverrideRejectedError(f"filter {key!r} has a non-scalar value")
            out[key] = list(value)
        else:
            # A nested container (dict / object) is refused: filters are scalar or a flat list of them.
            raise OverrideRejectedError(f"filter {key!r} must be a scalar or a list of scalars")
    return out


def _validate_comparison(widget: dict, raw: object) -> str | None:
    """Validate a single ``comparison`` selection, falling back to the widget's default."""
    allowed = frozenset((widget.get("controls") or {}).get("compare_by") or ())
    if raw is None:
        default = widget.get("default_compare_by")
        if default is None:
            return None
        if default not in allowed:
            raise OverrideRejectedError("default comparison is not permitted on this widget")
        return default
    if not isinstance(raw, str) or raw not in allowed:
        raise OverrideRejectedError("comparison is not permitted on this widget")
    return raw


def _validate_page(raw: object) -> int:
    """Validate a ``page`` selector: absent -> 1, else a positive int within the bound."""
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise OverrideRejectedError("page must be an integer")
    if not (1 <= raw <= _MAX_PAGE):
        raise OverrideRejectedError("page is out of range")
    return raw


def _validate_overrides(widget: dict, body: dict) -> tuple[dict | None, dict, str | None, list | None, int]:
    """Validate a request body against one widget and return the evaluator inputs.

    Order: the top-level key gate, then each permitted override. The returned ``grouping`` is derived
    from the single validated ``comparison`` selector so the caller cannot smuggle a second axis.
    """
    _check_top_keys(body)
    date_override = _validate_date(body.get("date"))
    filters = _validate_filters(widget, body.get("filters"))
    comparison = _validate_comparison(widget, body.get("comparison"))
    grouping = [comparison] if comparison else None
    page = _validate_page(body.get("page"))
    return date_override, filters, comparison, grouping, page


# ---------------------------------------------------------------------------
# Evaluation (the only place a row is ever read; callers trap domain errors -> frame error dict)
# ---------------------------------------------------------------------------
def _evaluate(
    layout: dict,
    widget: dict,
    *,
    date_override: dict | None = None,
    filters: dict | None = None,
    comparison: str | None = None,
    grouping: list | None = None,
    page: int = 1,
    rows: list | None = None,
) -> dict:
    """Evaluate one widget into a JSON-safe payload dict. NEVER raises for a domain failure."""
    if rows is None:
        rows = data.fetch_project_rows(_PROJECT_ID, layout_widget=widget)
    specs = _build_specs(layout)
    request = RequestContract(
        widget_id=widget["id"],
        date_override=date_override,
        filter_overrides=dict(filters or {}),
        comparison=comparison,
    )
    if grouping is None:
        grouping = [comparison] if comparison else None
    display = widget.get("type")
    buckets = widget.get("bucket") if display in ("line", "bar") else None
    ci_registry = {"positive_predictive_value"} if (widget.get("ci") or {}).get("enabled") else None
    policy = (widget.get("query") or {}).get("threshold_policy")
    is_table = display == "table"
    result = evaluate(
        request=request,
        project=get_project_definition(),
        catalog=None,
        rows=rows,
        ci_registry=ci_registry,
        grouping=grouping,
        buckets=buckets,
        page_size=_SERVER_PAGE_SIZE if is_table else None,
        max_groups=100,
        published_widget_ids=frozenset(specs),
        widgets=specs,
        include_rows=is_table,
    )
    payload = result.to_dict()
    if is_table:
        all_rows = list(result.rows)
        page_rows = all_rows[(page - 1) * _SERVER_PAGE_SIZE : page * _SERVER_PAGE_SIZE]
        payload["rows"] = page_rows
        payload["pagination"] = {
            "page": page,
            "page_size": _SERVER_PAGE_SIZE,
            "returned": len(page_rows),
            "truncated": page * _SERVER_PAGE_SIZE < len(all_rows),
        }
        visible_rows = bool(page_rows)
    else:
        visible_rows = False
    # ``empty`` is the single shared truth for "this frame measured nothing": an aggregate widget
    # with a zero matching population and a table with no rows in its page are both empty, while a
    # populated aggregate with zero rows (rows are withheld by contract) is NOT.
    counts = payload.get("counts") or {}
    payload["empty"] = (not visible_rows) and not counts.get("matching")
    return payload


_EMPTY_MESSAGE = (
    "No matching records in this window -- the dates or filters may exclude every "
    "record. Adjust the controls or reset them."
)


def _fmt_aggregate_value(value: object) -> str:
    """Render one aggregates-group value as compact, textContent-safe display text."""
    if isinstance(value, Mapping):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)
    return str(value)


def _summary_text(payload: dict) -> str:
    """A one-line, human-readable account of what the payload measured (or why it is empty)."""
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    counts = (payload or {}).get("counts")
    if not counts:
        return _EMPTY_MESSAGE
    matching = counts.get("matching")
    if not matching:
        return _EMPTY_MESSAGE
    text = (
        f"matching {matching} of {counts.get('incoming')} "
        f"\u00b7 {counts.get('eligible')} eligible for measurement"
    )
    coverage = ((payload or {}).get("dates") or {}).get("coverage_note")
    if coverage:
        text = f"{text} ({coverage})"
    return text


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
@login_required
@require_GET
def index(request):
    """Landing page listing the published reports. Renders no clinical data, touches no database."""
    try:
        published_reports = data.list_published(project_id=_PROJECT_ID)
    except Exception:  # the index must never fail because the definition tree is absent/broken
        published_reports = []
    return render(
        request,
        "report_v2/index.html",
        {
            "published_reports": published_reports,
            "legacy_report_url": reverse("report:index"),
        },
    )


@login_required
@require_GET
def report_page(request, slug: str):
    """Render one published report layout as a grid of server-hydrated, fault-isolated widget frames."""
    try:
        validate_definition_id(slug)
    except InvalidDefinitionIdError as exc:
        raise Resolver404(f"unknown report {slug!r}") from exc
    try:
        version, layout = data.load_published_layout(slug, _PROJECT_ID)
    except data.PublishedNotFoundError as exc:
        raise Resolver404(f"unknown report {slug!r}") from exc

    sections_ctx = []
    for section in layout.get("sections") or []:
        frames = []
        for widget in section.get("widgets") or []:
            widget_id = widget.get("id")
            try:
                payload = _evaluate(layout, widget)
            except Exception as exc:  # a single bad frame must not 500 the page or its siblings
                payload = {"widget_id": widget_id, "error": str(exc)}
            row_columns = (list(payload["rows"][0].keys())
                          if isinstance(payload, dict) and payload.get("rows") else [])
            row_cells = ([[row.get(key) for key in row_columns] for row in payload.get("rows") or []]
                        if row_columns else [])
            frames.append(
                {
                    "id": widget_id,
                    "title": widget.get("title"),
                    "type": widget.get("type"),
                    "width": (widget.get("layout") or {}).get("width"),
                    "height": (widget.get("layout") or {}).get("height"),
                    "controls": _allowed_controls(widget),
                    "context_token": _widget_context_token(slug, version, widget_id),
                    "data_url": reverse("report_v2:widget_data", args=[slug, widget_id]),
                    "payload": payload,
                    "summary": _summary_text(payload),
                    "empty_message": _EMPTY_MESSAGE,
                    # Pre-formatted aggregate rows for the server-side rendering: name/value pairs as
                    # plain strings so the template never iterates dict internals or emits raw markup.
                    "aggregates_view": [
                        {"name": str(key), "value": _fmt_aggregate_value(value)}
                        for key, value in (payload.get("aggregates") or {}).items()
                    ] if isinstance(payload, dict) and not payload.get("error") else [],
                    "has_rows": bool(isinstance(payload, dict) and payload.get("rows")),
                    "row_columns": row_columns,
                    "row_cells": row_cells,
                    # The view applies escape() itself so the template can mark this |safe; the
                    # embedded JSON can then never break out of the <pre> as markup.
                    "initial_json": escape(json.dumps(payload, default=str)),
                }
            )
        sections_ctx.append(
            {
                "id": section.get("id"),
                "title": section.get("title"),
                "widgets": frames,
            }
        )

    context = {
        "slug": slug,
        "version": version,
        "title": layout.get("title"),
        "grid": layout.get("grid") or {},
        "sections_ctx": sections_ctx,
        "is_admin": can_edit_catalog(request.user),
        "legacy_report_url": reverse("report:index"),
    }
    return render(request, "report_v2/page.html", context)


@login_required
@require_POST
@csrf_protect
def widget_data(request, slug: str, widget_id: str):
    """Return one widget's evaluated data as JSON, after every forged-input gate.

    Strict order; every rejection returns *before* a row is read, and no error body carries row data:

    1. body must be a JSON object;
    2. only allow-listed top-level keys;
    3. ids must be well-formed (else ``404``);
    4. the signed context token must verify and be bound to this ``(slug, current version, widget_id)``
       (tamper -> ``403``, pointer moved past the pinned version -> ``409``, absent report -> ``404``);
    5. the widget must exist in the current layout;
    6. every override must be permitted (else ``400``);
    7. the evaluation runs -- a domain error is reported as a ``200`` ``error`` status, never a ``500``;
    8. the payload is returned with the ``request_seq`` echoed back.
    """
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"error": "request body is not valid json", "status": "rejected"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "request body must be a json object", "status": "rejected"}, status=400)

    # (2) top-level allow-list on the raw body, before any interpretation or lookup.
    try:
        _check_top_keys(body)
    except OverrideRejectedError as exc:
        return JsonResponse({"error": str(exc), "status": "rejected"}, status=400)

    # (3) identifiers must be well-formed; a malformed id is simply "no such route" -> 404.
    try:
        validate_definition_id(slug)
        validate_definition_id(widget_id)
    except InvalidDefinitionIdError as exc:
        raise Resolver404(f"unknown report widget {slug!r}/{widget_id!r}") from exc

    # (4) verify the signed context token, then bind it to this request + the CURRENT pointer.
    try:
        token_slug, token_version, token_widget = _parse_widget_context(body.get("context"))
    except TamperedContextError:
        return JsonResponse({"error": "context token failed to verify", "status": "tampered"}, status=403)

    try:
        current_version, layout = data.load_published_layout(slug, _PROJECT_ID)
    except data.PublishedNotFoundError:
        return JsonResponse({"error": "report is not published", "status": "not_found"}, status=404)

    if (token_slug, token_version, token_widget) != (slug, current_version, widget_id):
        if token_version != current_version:
            # The version is pinned inside the signature; it cannot be changed by the request body.
            return JsonResponse({"error": "report version has changed; reload", "status": "stale"}, status=409)
        return JsonResponse({"error": "context does not match this widget", "status": "tampered"}, status=403)

    # (5) the widget must actually be on the current published layout.
    widget = _layout_widgets(layout).get(widget_id)
    if widget is None:
        return JsonResponse({"error": "widget is not on this layout", "status": "tampered"}, status=403)

    # (6) every permitted override, validated against the widget (no row is read here).
    try:
        date_override, filters, comparison, grouping, page = _validate_overrides(widget, body)
    except OverrideRejectedError as exc:
        return JsonResponse({"error": str(exc), "status": "rejected"}, status=400)

    # (7) the ONLY row read on this path; a domain error is data (200), not a server fault.
    try:
        rows = data.fetch_project_rows(_PROJECT_ID, layout_widget=widget)
        payload = _evaluate(
            layout,
            widget,
            date_override=date_override,
            filters=filters,
            comparison=comparison,
            grouping=grouping,
            page=page,
            rows=rows,
        )
    except (EvaluationError, data.AdapterError) as exc:
        return JsonResponse({"status": "error", "error": str(exc), "widget_id": widget_id}, status=200)

    # (8) echo the client's sequencing token (int-coerced when it is one) and return the payload.
    request_seq = body.get("request_seq")
    if request_seq is not None:
        try:
            request_seq = int(request_seq)
        except (TypeError, ValueError):
            request_seq = None
    return JsonResponse({"status": "ok", "request_seq": request_seq, **payload}, status=200)
