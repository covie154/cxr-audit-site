---
status: investigating
trigger: New V2 report Print button appears inactive
---
Evidence: _layout_widgets only traverses legacy sections; new report definitions store top-level widgets. report_page marks all unknown cards decorative, omitting their tokens; snapshot submissions cannot cover these cards. Scope includes widget data, CSV, snapshot and default API PDF callers. Also inspect asynchronous popup navigation and visible progress.

## Resolution (2026-11-09)
Eliminated initial flat-layout suspicion: load_report_definition normalizes flat widgets to sections; a synthetic newly published flat report successfully snapshots and prints temporary D-7 settings. No widget lookup changes made.

Confirmed code defect: window.open happened after awaiting the snapshot request, outside the original click activation. The click now reserves an about:blank tab synchronously, shows preparation status, navigates the reserved tab after success, offers a link if blocked/closed, and closes the placeholder on failure. No preference persistence or snapshot validation changes.

Verification: three new JS regressions cover activation timing, blocked-tab link, and failed snapshot cleanup. Real Chromium test exercised the shipped report module with a pending synthetic fetch and confirmed immediate tab plus successful navigation. Full focused JS suite passed (28 tests). Live user deployment has not been exercised.
