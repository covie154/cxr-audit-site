# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Snapshot-based export surface for report v2 (Task 17: print; Task 18 will add email).

Two endpoints, both login-gated, both built on the Task-13 forged-input discipline
(every rejection returns *before* a row is read):

* ``POST /report/<slug>/snapshot/`` -- freeze the *server-side* evaluation of every
  published widget under the caller's current overrides and hand back an opaque,
  scoped, bounded-lifetime snapshot token plus the print URL. The request must
  carry one entry per published widget (signed context token + that widget's
  overrides) and an explicit ``settled: true`` acknowledgement: while any widget
  update is still pending the client must NOT request an export, and a request
  without the acknowledgement is rejected with ``409 pending`` (the "block export
  while widget updates are pending" gate).
* ``GET /report/<slug>/print/<token>/`` -- render print-ready HTML from the frozen
  document ONLY. No re-evaluation, no ORM access, no cache of definitions: a page
  already rendered in the user's browser stays exportable even after the dataset
  or the published version moved on, and an expired/foreign/tampered snapshot fails
  with an explicit status + regenerate instruction instead of silently re-freezing
  under new definitions.

The print page is a standalone light-theme document (no app chrome, no widget
controls, no page-state contract): a snapshot is export state, never restored user
preferences. Charts render as accessible data tables straight from the frozen
payloads, so offscreen widgets and long tables print deterministically.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone as _tz
from typing import Any, Mapping

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from . import data, snapshots
from .definitions.repository import InvalidDefinitionIdError, validate_definition_id
from .evaluation import EvaluationError
from .views import (
    _PROJECT_ID,
    TamperedContextError,
    OverrideRejectedError,
    _evaluate,
    _layout_widgets,
    _parse_widget_context,
    _summary_text,
    _validate_overrides,
)

__all__ = ["create_snapshot", "print_view"]

#: The only top-level keys a snapshot-creation body may carry.
_SNAPSHOT_BODY_KEYS = frozenset({"settled", "widgets"})

#: The only keys one per-widget entry may carry (mirrors the widget-data allow-list:
#: date / filters / comparison / page are the sole user-controllable state).
_ENTRY_KEYS = frozenset({"context", "date", "filters", "comparison", "page"})

#: Document discriminator + view contract version frozen into every snapshot.
_SNAPSHOT_KIND = "report_v2_print_v1"


class _Rejected(Exception):
    """Internal carrier -> JsonResponse(rejected, 400)."""


# ---------------------------------------------------------------------------
# POST /report/<slug>/snapshot/ -- freeze the evaluated report server-side
# ---------------------------------------------------------------------------
def _entry_state(widget: dict, entry: dict) -> tuple[dict | None, dict, str | None, list | None, int]:
    """Validate one entry against one widget (delegates to the Task-13 validators)."""
    for key in entry:
        if key not in _ENTRY_KEYS:
            raise _Rejected(f"widget entry carries unexpected key {key!r}")
    if not isinstance(entry.get("context"), str) or not entry["context"]:
        raise _Rejected("widget entry is missing its signed context token")
    return _validate_overrides(widget, entry)


@login_required
@require_POST
@csrf_protect
def create_snapshot(request, slug: str):
    """Freeze every published widget under the caller's current state; return the print URL.

    Order of gates (mirrors :func:`report_v2.views.widget_data`; each returns before a
    row is read): body shape -> ``settled`` acknowledgement -> well-formed slug ->
    published layout -> full, duplicate-free widget coverage -> per-entry context
    verification + override validation -> the single evaluation pass per widget.
    """
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"error": "request body is not valid json", "status": "rejected"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "request body must be a json object", "status": "rejected"}, status=400)
    for key in body:
        if key not in _SNAPSHOT_BODY_KEYS:
            return JsonResponse({"error": f"unexpected top-level key {key!r}", "status": "rejected"}, status=400)

    # The pending gate: the client must confirm every widget update has settled.
    if body.get("settled") is not True:
        return JsonResponse(
            {"error": "widget updates are still pending; retry once they have settled",
             "status": "pending"},
            status=409,
        )

    try:
        validate_definition_id(slug)
    except InvalidDefinitionIdError as exc:
        raise Resolver404(f"unknown report {slug!r}") from exc
    try:
        version, layout = data.load_published_layout(slug, _PROJECT_ID)
    except data.PublishedNotFoundError:
        return JsonResponse({"error": "report is not published", "status": "not_found"}, status=404)

    layout_widgets = _layout_widgets(layout)
    entries = body.get("widgets")
    if not isinstance(entries, list) or not entries:
        return JsonResponse({"error": "widgets must be a non-empty list", "status": "rejected"}, status=400)
    if len(entries) > snapshots.MAX_SNAPSHOT_WIDGETS:
        return JsonResponse(
            {"error": f"too many widget entries (bound {snapshots.MAX_SNAPSHOT_WIDGETS})",
             "status": "rejected"},
            status=400,
        )
    if len(entries) != len(layout_widgets):
        return JsonResponse(
            {"error": "snapshot must cover every published widget exactly once",
             "status": "rejected"},
            status=400,
        )

    # Verify every entry (context + overrides) before ANY row is read.
    plan: list[tuple[dict, dict, dict | None, dict, str | None, list | None, int]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return JsonResponse({"error": "widget entry must be an object", "status": "rejected"}, status=400)
        try:
            token_slug, token_version, widget_id = _parse_widget_context(entry.get("context"))
        except TamperedContextError:
            return JsonResponse({"error": "context token failed to verify", "status": "tampered"}, status=403)
        # The widget id is read back out of the verified token only -- an unsigned
        # body field can never re-scope an entry.
        if (token_slug, token_version) != (slug, version):
            if token_version != version:
                return JsonResponse({"error": "report version has changed; reload",
                                     "status": "stale"}, status=409)
            return JsonResponse({"error": "context does not match this report", "status": "tampered"}, status=403)
        if widget_id in seen:
            return JsonResponse({"error": f"widget {widget_id!r} appears twice",
                                 "status": "rejected"}, status=400)
        widget = layout_widgets.get(widget_id)
        if widget is None:
            return JsonResponse({"error": "widget is not on this layout", "status": "tampered"}, status=403)
        seen.add(widget_id)
        try:
            date_override, filters, comparison, grouping, page = _entry_state(widget, entry)
        except (_Rejected, OverrideRejectedError) as exc:
            return JsonResponse({"error": str(exc), "status": "rejected"}, status=400)
        plan.append((widget, entry, date_override, filters, comparison, grouping, page))

    if seen != set(layout_widgets):
        return JsonResponse({"error": "snapshot must cover every published widget exactly once",
                             "status": "rejected"}, status=400)

    # The evaluation pass: one ORM read per widget, fault-isolated per frame (a bad
    # widget freezes its error string exactly like the page render does).
    frozen_widgets: list[dict[str, Any]] = []
    for widget, entry, date_override, filters, comparison, grouping, page in plan:
        try:
            rows = data.fetch_project_rows(_PROJECT_ID, layout_widget=widget)
            payload = _evaluate(
                layout, widget,
                date_override=date_override, filters=filters,
                comparison=comparison, grouping=grouping, page=page, rows=rows,
            )
        except (EvaluationError, data.AdapterError) as exc:
            payload = {"widget_id": widget.get("id"), "error": str(exc)}
        except Exception as exc:  # fault isolation: one frame must not kill the export
            payload = {"widget_id": widget.get("id"), "error": str(exc)}
        frozen_widgets.append(
            {
                "widget_id": widget.get("id"),
                "title": widget.get("title"),
                "type": widget.get("type"),
                "section_id": None,
                "applied": {
                    "date": entry.get("date"),
                    "filters": dict(filters or {}),
                    "comparison": comparison,
                    "page": page,
                },
                "payload": payload,
            }
        )

    document = {
        "kind": _SNAPSHOT_KIND,
        "project_id": _PROJECT_ID,
        "slug": slug,
        "version": version,
        "title": layout.get("title"),
        "generated": datetime.now(_tz.utc).isoformat(),
        "widgets": frozen_widgets,
    }
    token = snapshots.create_snapshot(
        user_id=request.user.pk,
        project_id=_PROJECT_ID,
        slug=slug,
        document=document,
        ttl=snapshots.DEFAULT_SNAPSHOT_TTL,
    )
    return JsonResponse(
        {
            "status": "ok",
            "print_url": reverse("report_v2:print", args=[slug, token]),
            "expires_in": snapshots.DEFAULT_SNAPSHOT_TTL,
        },
        status=201,
    )


# ---------------------------------------------------------------------------
# GET /report/<slug>/print/<token>/ -- render the frozen document, nothing else
# ---------------------------------------------------------------------------
@login_required
@require_GET
def print_view(request, slug: str, snap_token: str):
    """Render print-ready HTML from the frozen snapshot (no re-evaluation, no ORM)."""
    try:
        document = snapshots.load_snapshot(
            snap_token, user_id=request.user.pk, project_id=_PROJECT_ID, slug=slug
        )
    except snapshots.SnapshotExpiredError as exc:
        return HttpResponse(str(exc), status=410, content_type="text/plain")
    except snapshots.SnapshotForeignError as exc:
        return HttpResponse(f"{exc} It cannot be viewed from this report page.", status=403,
                            content_type="text/plain")
    except snapshots.SnapshotTamperedError as exc:
        return HttpResponse(str(exc), status=403, content_type="text/plain")

    if document.get("kind") != _SNAPSHOT_KIND:
        return HttpResponse("snapshot token failed to verify", status=403, content_type="text/plain")

    return render(
        request,
        "report_v2/print.html",
        {"print": _print_view_model(document)},
    )


# ---------------------------------------------------------------------------
# Print view-model (pure; consumes the frozen document only)
# ---------------------------------------------------------------------------
def _fmt(value: Any) -> str:
    """One textContent-safe cell value: ``None`` -> em dash, containers -> readable text."""
    if value is None:
        return "—"
    if isinstance(value, Mapping):
        return ", ".join(f"{k}={_fmt(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return " | ".join(_fmt(item) for item in value)
    return str(value)


def _table(caption: str, columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {"caption": caption, "columns": columns, "rows": rows}


def _applied_line(applied: Mapping[str, Any]) -> str:
    """One line describing the widget state that was frozen (dates/filters/grouping/page)."""
    parts: list[str] = []
    date = applied.get("date")
    if isinstance(date, Mapping):
        if "relative" in date:
            parts.append(f"window {date['relative']}")
        else:
            parts.append(f"dates {date.get('start')}..{date.get('end')}")
    filters = applied.get("filters") or {}
    for key in sorted(filters):
        parts.append(f"{key}={_fmt(filters[key])}")
    if applied.get("comparison"):
        parts.append(f"compare by {applied['comparison']}")
    if applied.get("page") and int(applied["page"] or 1) > 1:
        parts.append(f"page {applied['page']}")
    return "; ".join(parts) if parts else "default window and filters"


def _counts_line(payload: Mapping[str, Any]) -> str:
    counts = payload.get("counts") or {}
    if not counts:
        return ""
    text = (
        f"matching {counts.get('matching')} of {counts.get('incoming')}"
        f" · {counts.get('eligible')} eligible for measurement"
    )
    reasons = counts.get("excluded_by_reason") or {}
    if reasons:
        detail = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
        text += f" · excluded: {detail}"
    return text


def _bucket_label(payload: Mapping[str, Any], index: Any) -> str:
    buckets = payload.get("buckets") or []
    try:
        bucket = buckets[int(index)]
    except (TypeError, ValueError, IndexError):
        return _fmt(index)
    if not isinstance(bucket, Mapping):
        return _fmt(index)
    label = bucket.get("label")
    if label:
        return str(label)
    start, end = bucket.get("start"), bucket.get("end")
    if start and end:
        return f"{start}..{end}"
    return _fmt(index)


def _widget_tables(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Render the frozen payload as print tables: aggregates, rows, and chart contracts."""
    tables: list[dict[str, Any]] = []
    chart = payload.get("chart") or {}

    aggregates = payload.get("aggregates") or {}
    matrix = aggregates.get("matrix")
    if isinstance(matrix, Mapping) and chart.get("cells"):
        classes = [str(c) for c in chart.get("classes") or []]
        cells = chart["cells"]
        totals = chart.get("row_totals") or [None] * len(cells)
        rows = []
        for i, gt_class in enumerate(classes):
            row = [gt_class] + [_fmt(cells[i][j]) for j in range(len(classes))]
            row.append(_fmt(totals[i]))
            rows.append(row)
        tables.append(_table(
            str(chart.get("caption") or "Ground truth (rows) vs prediction (columns)"),
            ["GT \\ Pred"] + classes + ["Total"], rows,
        ))
    elif aggregates:
        tables.append(_table(
            "Measured values",
            ["Measure", "Value"],
            [[str(k), _fmt(v)] for k, v in aggregates.items()],
        ))

    if isinstance(payload.get("rows"), list) and payload["rows"]:
        columns: list[str] = []
        for row in payload["rows"]:
            for key in row:
                if key not in columns:
                    columns.append(key)
        tables.append(_table(
            "Case rows",
            columns,
            [[_fmt(row.get(col)) for col in columns] for row in payload["rows"]],
        ))
        pagination = payload.get("pagination") or {}
        if pagination.get("truncated"):
            tables.append(_table(
                "Table pagination",
                ["Property", "Value"],
                [["shown", str(pagination.get("returned"))],
                 ["page", str(pagination.get("page"))],
                 ["page size", str(pagination.get("page_size"))],
                 ["more rows", "yes — regenerate the snapshot on a later page to print them"]],
            ))

    series = chart.get("series")
    if isinstance(series, list) and series:
        rows = []
        for cell in series:
            label = (_bucket_label(payload, cell.get("bucket_index"))
                     if cell.get("bucket_index") is not None else _fmt(cell.get("category")))
            rows.append([_fmt(cell.get("group")), label, _fmt(cell.get("value"))])
        tables.append(_table("Chart data (series)", ["Series", "Period", "Value"], rows))

    categories = chart.get("categories")
    if isinstance(categories, list) and categories:
        tables.append(_table(
            "Chart data (categories)",
            ["Category", "Count"],
            [[_fmt(c.get("label")), _fmt(c.get("count"))] for c in categories],
        ))

    summaries = chart.get("summaries")
    if isinstance(summaries, list) and summaries:
        rows = []
        for item in summaries:
            summary = item.get("summary") or {}
            for key, value in summary.items():
                rows.append([_fmt(item.get("name")), str(key), _fmt(value)])
        if rows:
            tables.append(_table("Chart data (distribution summary)", ["Series", "Statistic", "Value"], rows))

    return tables


def _print_view_model(document: Mapping[str, Any]) -> dict[str, Any]:
    """Template context for ``print.html`` -- everything derives from the frozen document."""
    widgets: list[dict[str, Any]] = []
    for widget in document.get("widgets") or []:
        payload = widget.get("payload") or {}
        if not isinstance(payload, Mapping):
            payload = {}
        error = payload.get("error")
        dates = payload.get("dates") or {}
        versions = payload.get("versions") or {}
        widgets.append(
            {
                "id": widget.get("widget_id"),
                "title": widget.get("title"),
                "type": widget.get("type"),
                "error": str(error) if error else "",
                "summary": _summary_text(payload) if not error else str(error),
                "applied_line": _applied_line(widget.get("applied") or {}),
                "counts_line": _counts_line(payload) if not error else "",
                "window": f"{dates.get('window_start') or '?'} .. {dates.get('window_end') or '?'}",
                "anchor": dates.get("anchor_date") or "—",
                "timezone": dates.get("timezone") or "",
                "coverage": dates.get("coverage_note") or "",
                "measurement": versions.get("measurement_id") or "",
                "policy": versions.get("policy_ref") or "—",
                "tables": [] if error else _widget_tables(payload),
            }
        )
    return {
        "slug": document.get("slug"),
        "version": document.get("version"),
        "title": document.get("title"),
        "project_id": document.get("project_id"),
        "generated": document.get("generated"),
        "widgets": widgets,
    }
