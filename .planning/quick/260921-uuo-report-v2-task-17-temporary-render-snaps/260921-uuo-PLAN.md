---
status: done
---
# Task 17: Temporary render snapshots and print flow

Scope: runbook Task 17 (`.planning/report-v2/EXECUTION-RUNBOOK.md`). Work inline in the
current checkout; repository root is the workspace root with its existing `.planning`/`.git`.
Task 18 (email) stays out of scope.

1. Implement `report_v2/snapshots.py`: a small explicitly scoped transient store (Django
   `FileBasedCache` under a private root, `settings.REPORT_V2_SNAPSHOT_ROOT` overridable,
   default `private_data/report_v2_snapshots` — cross-worker safe, no new dependency) holding
   frozen evaluated widget payloads + report/policy versions + per-widget overrides. Opaque IDs
   are server-signed (domain-separated salt) and bound to user/project/slug with a bounded TTL
   (default 900 s). Foreign/expired/tampered loads fail with typed errors; payload and widget
   counts are bounded; a snapshot is never returned as page state.
2. Implement `report_v2/exports.py`: `POST /report/<slug>/snapshot/` (login + CSRF) that
   requires the full published widget set (each entry: signed context token + validated
   overrides, reusing the Task-13 validators), rejects `settled != true` with 409 pending,
   re-evaluates every widget server-side through the single ORM seam, and freezes the result
   (fault-isolated per widget). `GET /report/<slug>/print/<token>/` renders print-ready HTML
   from the frozen snapshot only — no re-evaluation, no ORM — with explicit 403 tampered /
   403 foreign / 410 expired(+regenerate message) failures and a server-side light-theme
   view-model (aggregates, case rows + pagination note, chart series/categories/summaries/
   matrix as accessible tables).
3. Add `templates/report_v2/print.html` + `static/report_v2/print.css` (light palette, print
   page-break rules, repeated table headers, offscreen-safe static rendering) and a page.html
   print affordance plus report.js flow that waits for all in-flight widget updates to settle
   before requesting a snapshot, then opens the print URL (browser Save-as-PDF preserved).
4. Focused tests: `tests/test_snapshots.py` (store semantics) and `tests/test_print.py`
   (endpoint security + freeze/immutability against later data changes and republishing,
   per-widget dates/filters/grouping/versions in output, no-preference-restore, pending gate,
   CSRF/login, oversized-table note). Run report_v2 + lunit_audit suites, `node --check` on
   report.js, the node test suites, and `git diff --check`.
5. Record evidence in `IMPLEMENTATION-NOTES.md`, commit scoped Task-17 paths, update the GSD
   summary and `STATE.md`. No clinical DB access, no publishing of production seeds, no
   deployment, no real email.

## Completion summary (2026-09-21)

All five steps executed. 24 new tests (test_snapshots 12, test_print 12); report_v2 433 OK,
lunit_audit 16 OK; node --check report.js OK; node --test 72/72; git diff --check clean.
Files: snapshots.py, exports.py, print.html, print.css, urls.py (2 appended routes),
page.html (print affordance), report.js (snapshot/print flow). Full evidence in
IMPLEMENTATION-NOTES.md "Task 17".
