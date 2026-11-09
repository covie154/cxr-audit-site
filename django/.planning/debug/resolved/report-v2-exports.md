---
status: resolved
trigger: Slow Report V2 print/PDF and email; pending status persists, fallback opens same window, charts become tables.
created: 2026-11-09
updated: 2026-11-09
---

## Symptoms
Expected: prompt print in a separate window, with print and email preserving web report charts and layout.
Actual: prolonged pending status, manual fallback link and table-based output (user-supplied PDF).
Reproduction: Print / Save as PDF or Email report on a loaded Report V2 page.

## Current Focus
hypothesis: Confirmed repeated snapshot evaluation, misleading status, missing link target, and export presentation defects.
next_action: Rebuild/restart the deployed Django application and refresh collected static assets; source changes verified locally.

## Scope
Shared report runtime; server snapshot generation; print module/template/styles; email images/template; focused JS, Django and browser regressions. Preserve signed contexts, user/project scoping, validation and case-table disclosure controls.

## Evidence
Snapshot freeze fetches every study once per widget. Waiting status is not updated when server snapshot generation starts. Print fallback has no target. Email capture failures silently substitute tables.

## Workspace
Actual Git checkout and django-app are at workspace root despite old boundary wording. Keep planning in django/.planning and do not change Git metadata or commit.

## Resolution
- Cache successful server widget payloads in the existing private, bounded, file-backed snapshot store for 15 minutes. Keys bind signed context, widget definition, controls, user and session. All snapshot validation still precedes lookup; misses evaluate normally. Script-free API exports continue evaluating fresh defaults.
- Separate pending-update and snapshot-preparation status. Retry only actual pending responses, not stale publication errors. Keep tab reservation during the user click; fallback links explicitly open a new tab with noopener.
- Capture chart images before snapshot creation; capture failures produce an explicit error instead of silently substituting tables.
- Print uses stable data attributes for chart dimensions, preserves matrix heatmaps, constrains accessibility tables to prevent page overflow, and enables printing only after rendering succeeds.
- Email preserves chart images, grouped/calendar values and confidence intervals, calendar matrix heatmaps, actual summary-table rows and partial-width card layout. Case-row disclosure caps remain in force.
- Supplied PDF contains a table-only template shape differing from this checkout; deployment/template/static mismatch is inferred. No clinical database was read during verification.

## Verification
- 71 Django tests passed: print, email, visual exports, pages, snapshots, navigation and static modules.
- 22 JavaScript tests passed: page state/runtime bridge, print button, image capture.
- Chromium journey passed across all seven widget types using 2,000 synthetic studies: separate print tab, rendered charts, heatmaps visible under print media, no collapsed canvas or horizontal page overflow, captured inline email PNGs, successful locmem send, formatted email summary rows and frozen card widths.
- Latest loaded-report print readiness: 0.31 seconds on the local synthetic fixture (not a production benchmark).
- Reviewed synthetic print and email screenshots under the system temporary primer-export-evidence directory.
- git diff --check passed. No dependencies added. Original user PDF untouched.

## Limits and handoff
- Not deployed or committed; actual checkout Git metadata is at workspace root and was not modified.
- Live SMTP, real email clients and the operating-system print dialog were not exercised.
- Cache entries expire or may be evicted under the existing store budget; those exports evaluate afresh.
- Rebuild/restart Django and refresh collected static assets to apply source changes to the running instance.

