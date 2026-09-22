---
status: complete
---
# Task 19: End-to-end acceptance and handoff — complete

Quick task (acceptance round), executed 2026-09-22. Runbook Task 19, the final task of
`.planning/report-v2/EXECUTION-RUNBOOK.md`. Commit: `8477d8e`
("test(report): task 19 end-to-end acceptance suite over the runbook checklist").
The runbook's 12-item final acceptance checklist is ticked in EXECUTION-RUNBOOK.md with
per-item evidence recorded in IMPLEMENTATION-NOTES.md "Task 19".

## What was done

- **Full-suite run**: `python manage.py test --noinput` → 462 tests OK (skipped=1
  pre-existing Windows symlink skip) — report_v2 437 (431 + 6 new acceptance),
  lunit_audit/audit/upload 25, including the real-Chromium browser suites.
- **New `tests/test_acceptance_e2e.py` (6 tests)**: the editor→publish→viewer→per-widget
  filters→snapshot→print→email→duplicate-guard journey over synthetic data; two-report
  independence with pinned versions; legacy `/report-old/` preservation; collectstatic
  into an isolated temp root with the production WhiteNoise manifest storage;
  nothing-forbidden scans (no PDF engine/scheduler/attachments/storage APIs); seed YAML
  shape (17 widgets, seven display types, no text box, export flags declared).
- **Reviews recorded with pointers**: responsive layout (1440/1024/390 browser
  screenshots), older-subgroup message (preserved D + exposed subgroup latest date),
  CI control (Wilson, registered combos, admin-owned), initial YAML (seed --check).
- **Project isolation** re-verified via the test-only synthx adapter suite.
- **Handoff** written into IMPLEMENTATION-NOTES.md: task lineage T01–T19 commit IDs,
  configuration changes (REPORT_V2_ROOT / REPORT_V2_SNAPSHOT_ROOT, both optional with
  private defaults), seed procedure (check → admin seed draft → explicit publish),
  rollback (/report-old/ fallback, per-task revert units, private_data survives), and
  an explicit known-limitations list (single-host snapshot store, compose volume mounts
  deferred, print charts as static tables, client-captured email images, HTTP-level
  modal coverage, policy v2 fixtures-only).

## Final verification battery (from django-app/, CPython 3.13.5)

- `python manage.py test --noinput` → Ran 462 tests OK (skipped=1)
- `python manage.py seed_report_v2 --check` → SEED-CHECK OK overview 17 widgets
- `node --test report_v2/tests/js/` → 72/72; `node --check` report.js/editor.js OK
- `git diff --check` → clean

No clinical records viewed, no external email sent, no deployment. All 19 runbook tasks
are now complete; the report-v2 rebuild is finished pending separately-authorised
deployment.
