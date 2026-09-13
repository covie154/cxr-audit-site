# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Read-only published-layout access plus the single CXRStudy -> evaluator row adapter.

Task 13's data seam. Two responsibilities, both strictly read-only:

1. ``list_published`` / ``load_published_layout`` / ``load_published_layout_at`` read the published
   report layout from the private ``DefinitionRepository`` tree. They never write, never ``mkdir`` at
   import time, and never fall back to a *draft* -- an unpublished (draft-only) report is simply not
   visible here. ``list_published`` deliberately scans the ``pointers``/``blobs`` directories by hand
   instead of constructing a :class:`DefinitionRepository` (whose ``__init__`` creates directories), so
   rendering the index page cannot mutate the filesystem nor crash when the tree is absent.

2. ``fetch_project_rows`` is the *only* place the report-v2 web tier touches the ORM. It adapts
   ``upload.CXRStudy`` rows into the logical mappings the Task-10 evaluator consumes and is the single
   seam the page tests monkeypatch (``unittest.mock.patch("report_v2.data.fetch_project_rows", ...)``).

Security posture: every clinical column read here is a *pass-through* of the stored value -- label /
score values reach the row unmapped and un-thresholded because policy thresholding is Task 05's
registered classification concern, not this adapter's. A widget whose ``query.cohort`` names a cohort
this adapter does not know how to evaluate raises :class:`AdapterError` rather than inventing a
clinical rule; an unknown catalog ``source_id`` likewise raises rather than reading an arbitrary column.
``CXRStudy`` is imported *inside* ``fetch_project_rows`` so importing this module never requires the
database/apps registry to be ready.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from .definitions.loader import DefinitionError, load_report_definition
from .definitions.repository import (
    DefinitionRepository,
    InvalidDefinitionIdError,
    default_root,
    validate_definition_id,
)
from .projects.base import UnknownSourceError
from .projects.prime import get_project_definition

__all__ = [
    "PublishedNotFoundError",
    "AdapterError",
    "list_published",
    "load_published_layout",
    "load_published_layout_at",
    "fetch_project_rows",
]

_log = logging.getLogger(__name__)

#: Relative window-token start forms (``D``/``W``/``M``/``Y`` with an optional ``-n`` offset).
_RELATIVE_START_RE = re.compile(r"^(?:D|W|M|Y)(?:-\d+)?$")

#: The only cohort id this adapter knows how to restrict on; anything else is refused (no invented rule).
_SUPPORTED_COHORTS = frozenset({"manual_gt_subset"})


class PublishedNotFoundError(Exception):
    """No *published* layout is resolvable for the requested definition id."""


class AdapterError(Exception):
    """A layout widget cannot be safely adapted to ``CXRStudy`` columns (unknown source / cohort)."""


# ---------------------------------------------------------------------------
# Published-layout access (read-only; never touches drafts, never mkdirs at import)
# ---------------------------------------------------------------------------
def _safe_version_token(version: object) -> bool:
    """True when ``version`` is usable as a single blob filename component (no traversal, non-empty)."""
    if not isinstance(version, str) or not version:
        return False
    return "/" not in version and "\\" not in version and ".." not in version and "\x00" not in version


def list_published(project_id: str = "prime") -> list[dict[str, Any]]:
    """Summarise every *published* report for the index page.

    Scans ``default_root()/pointers`` and ``default_root()/blobs`` directly (never through
    :class:`DefinitionRepository`, whose constructor would create directories) and returns one entry
    per definition id whose pointer and blob both resolve::

        {"slug", "version", "title", "section_count"}

    A missing tree yields ``[]``. Any per-entry problem (a pointer whose blob is gone, an unparseable
    blob) is *skipped silently* -- the index page must never fail because one report is broken. The
    result is sorted by slug.
    """
    root = default_root()
    pointers = root / "pointers"
    blobs = root / "blobs"
    if not pointers.is_dir() or not blobs.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for pointer in sorted(pointers.iterdir(), key=lambda p: p.name):
        if not pointer.is_file():
            continue
        def_id = pointer.name
        try:
            validate_definition_id(def_id)
        except InvalidDefinitionIdError:
            continue
        try:
            version = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not _safe_version_token(version):
            continue
        blob = blobs / f"{version}.yaml"
        if not blob.is_file():
            continue
        try:
            data = load_report_definition(blob.read_text(encoding="utf-8"))
        except (DefinitionError, OSError):
            # A single broken published report must not crash the whole index listing.
            continue
        entries.append(
            {
                "slug": def_id,
                "version": version,
                "title": data.get("title"),
                "section_count": len(data.get("sections") or []),
            }
        )
    entries.sort(key=lambda entry: entry["slug"])
    return entries


def _read_current(def_id: str, project_id: str, *, pinned: str | None = None) -> tuple[str, dict[str, Any]]:
    """Shared loader for the current (or a pinned) published version; raises PublishedNotFoundError.

    Containment of the blob path is :meth:`DefinitionRepository._blob_path`'s responsibility; this
    function never falls back to a draft and never reads outside the published blob tree.
    """
    repo = DefinitionRepository(default_root(), project_id=project_id)
    try:
        current = repo.get_current_version(def_id)
    except InvalidDefinitionIdError as exc:
        raise PublishedNotFoundError(f"invalid definition id {def_id!r}") from exc
    if current is None:
        raise PublishedNotFoundError(f"no published version for {def_id!r}")
    if pinned is not None and pinned != current:
        raise PublishedNotFoundError(
            f"pinned version {pinned!r} is not the current version {current!r} of {def_id!r}"
        )
    try:
        path = repo._blob_path(def_id, current)
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublishedNotFoundError(f"published blob for {def_id!r}@{current!r} is unreadable") from exc
    try:
        data = load_report_definition(text)
    except DefinitionError as exc:
        raise PublishedNotFoundError(f"published layout for {def_id!r}@{current!r} is unparseable") from exc
    return current, data


def load_published_layout(def_id: str, project_id: str = "prime") -> tuple[str, dict[str, Any]]:
    """Return ``(version_token, parsed_layout)`` for the CURRENT published pointer.

    Raises :class:`PublishedNotFoundError` when there is no pointer, the blob is missing, or the blob
    does not parse. Drafts are never consulted on this path.
    """
    return _read_current(def_id, project_id)


def load_published_layout_at(def_id: str, version: str, project_id: str = "prime") -> tuple[str, dict[str, Any]]:
    """Like :func:`load_published_layout` but only when ``version`` equals the current pointer token."""
    return _read_current(def_id, project_id, pinned=version)


# ---------------------------------------------------------------------------
# CXRStudy -> evaluator row adapter (the single ORM seam; monkeypatched by the page tests)
# ---------------------------------------------------------------------------
def _as_float(value: object) -> float | None:
    """Coerce a stored duration/score to a float, or ``None`` when it is not a usable number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore
    except (TypeError, ValueError):
        return None


def _event_date(value: object) -> object:
    """Normalise ``procedure_start_date`` to a date / ISO string the evaluator's date parser accepts."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return value


def _map_inputs(row: dict[str, Any], study: Any, inputs: dict[str, Any], measurement: str | None, project: Any) -> None:
    """Bind each declared widget ``query.inputs`` role to a physical ``CXRStudy`` value on ``row``."""
    for role, source_id in (inputs or {}).items():
        try:
            physical = project.source(str(source_id)).field
        except UnknownSourceError as exc:
            raise AdapterError(f"widget input {source_id!r} is not a known {project.project_id} source") from exc
        value = getattr(study, physical, None)
        if role == "ground_truth":
            row["gt_label"] = value
        elif role == "prediction":
            row["pred_label"] = value
        elif role == "value":
            if measurement == "duration_summary":
                row["duration_seconds"] = _as_float(value)
            else:
                row[physical] = value
        else:
            row[physical] = value


def fetch_project_rows(
    project_id: str = "prime",
    *,
    layout_widget: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Adapt every ``upload.CXRStudy`` row into an evaluator input mapping (the single ORM seam).

    A base row is built per study::

        accession   <- accession_no
        event_date  <- procedure_start_date (.date() for a datetime, ISO string otherwise, else unset)
        site        <- workplace

    ``complete`` / ``missing_field`` / ``eligible`` / ``cross_project`` are left unset so the
    evaluator's own defaults apply (and so "same-project by construction" holds: ``cross_project``
    never becomes truthy here). Widget-scoped roles are then bound through the project catalog; see
    :func:`_map_inputs`. ``query.cohort`` absent -> ``eligible=True``; the single supported cohort
    ``manual_gt_subset`` -> ``eligible = gt_manual is not None``; any other cohort id is an
    :class:`AdapterError`. Rows are ordered by ``accession_no`` for determinism.
    """
    from upload.models import CXRStudy  # local import: keep DB/apps out of module import time

    project = get_project_definition()
    query = (layout_widget or {}).get("query", {}) or {}
    inputs = query.get("inputs", {}) or {}
    measurement = query.get("measurement")
    cohort = query.get("cohort")
    if cohort not in (None, "") and cohort not in _SUPPORTED_COHORTS:
        # Refuse to fabricate a clinical population rule for a cohort this adapter cannot evaluate.
        raise AdapterError(f"unsupported cohort {cohort!r}; this adapter knows only {sorted(_SUPPORTED_COHORTS)}")

    queryset = CXRStudy.objects.all().order_by("accession_no")
    if limit is not None:
        queryset = queryset[:limit]

    rows: list[dict[str, Any]] = []
    for study in queryset:
        row: dict[str, Any] = {"accession": study.accession_no, "site": study.workplace}
        event = _event_date(getattr(study, "procedure_start_date", None))
        if event is not None:
            row["event_date"] = event

        _map_inputs(row, study, inputs, measurement, project)

        if cohort in (None, ""):
            row["eligible"] = True
        elif cohort == "manual_gt_subset":
            row["eligible"] = getattr(study, "gt_manual", None) is not None
        rows.append(row)
    return rows
