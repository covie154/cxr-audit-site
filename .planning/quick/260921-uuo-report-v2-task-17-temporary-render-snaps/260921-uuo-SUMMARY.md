---
status: complete
---
# Task 17: Temporary render snapshots and print flow — complete

Quick task 260921-uuo, executed 2026-09-21. Runbook Task 17 of
`.planning/report-v2/EXECUTION-RUNBOOK.md`. Commit: `5988ea2`
("feat(report): task 17 transient render snapshots and print flow", 9 files, +1636).

## What was built

- `report_v2/snapshots.py` — transient, explicitly scoped snapshot store: Django
  `FileBasedCache` under a private configurable root (default
  `private_data/report_v2_snapshots`; works across gunicorn workers, no new dependency),
  server-signed opaque ids bound to user/project/slug with a bounded TTL (default 900 s),
  typed disjoint failures for tampered / foreign / expired (regenerate message), and hard
  widget-count / size / plain-data bounds.
- `report_v2/exports.py` — `POST /report/<slug>/snapshot/` (login + CSRF; requires
  `settled: true` → 409 pending gate; exact published-widget coverage; per-entry signed
  context verification + Task-13 override validation; server-side re-evaluation through
  the single ORM seam, fault-isolated per widget) and `GET
  /report/<slug>/print/<token>/` (renders the frozen document only — no re-evaluation, no
  ORM; 403 tampered / 403 foreign / 410 expired).
- `templates/report_v2/print.html` + `static/report_v2/print.css` — standalone
  always-light print document: per-widget window/anchor/timezone/coverage, applied
  dates/filters/grouping/page, count reconciliation, measurement + policy, and accessible
  tables (aggregates, case rows + pagination note, chart series/categories/summaries,
  confusion matrix); page-break-safe, repeated table headers, browser Save-as-PDF kept.
- `page.html` print button + `report.js` flow: blocks export until every widget update
  settles (in-flight + pendingSeq/lastAppliedSeq check, bounded poll), then freezes and
  opens the print view; nothing is restored into page state.
- `urls.py`: two appended routes (snapshot, print); nothing existing changed.

## Done-when verification

Every widget exports its own current dates, filters, grouping and metadata (named test
asserts window/anchor/site filter/comparison/D-7 override per widget). Later data changes
or publication do not alter the captured export (seam monkeypatched to AssertionError and
a v2 republication both leave the r1 print intact). Foreign/expired/tampered snapshots
fail explicitly (403/403/410 with regenerate message). A snapshot is not restored as user
preferences (print page carries no page-state contract; live page defaults unaffected).
Offscreen charts and long tables print correctly in light mode (static server-side
tables; truncated tables emit a pagination block).

## Test evidence (Windows host, CPython 3.13.5, from django-app/)

- test_snapshots 12 OK; test_print 12 OK (24 new tests).
- `report_v2` full suite: 417 OK (skipped=1 pre-existing symlink skip).
- `lunit_audit`: 16 OK. `node --test`: 72/72. `node --check report.js`/`editor.js`: OK.
- `seed_report_v2 --check`: SEED-CHECK OK overview 17 widgets. `git diff --check`: clean.

No clinical data accessed, nothing published to production seeds, no deployment, no email.
Task 18 (snapshot-based HTML email) is next and was not started.
