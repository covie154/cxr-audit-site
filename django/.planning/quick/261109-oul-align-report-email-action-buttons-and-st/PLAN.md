# Quick task 261109-oul: email actions and compact metadata

Date: 2026-11-09

## Scope
- Place Send and Cancel side by side, with an accessible live status area on their right.
- Show Sending report..., then persistent Report Sent or Error: ...; retain preparing/pending messages while those operations run.
- Match print card metadata in HTML and plain-text email: date window and applied state only.
- Update affected email assertions and the existing isolated Chromium journey, including sending, success, error and narrow modal layout.
- Preserve recipients, note, chart capture, report content, snapshot validation and email disclosure caps.

## Execution
Use the existing form/runtime/styles and export view model. No new dependency or service changes.

## Verification
Focused Django email/visual-export tests and the synthetic browser journey. Review the modal screenshot and git diff --check.

## Workspace
Planning remains under django/.planning per project instructions. The actual Git metadata is at workspace root; do not create commits outside the instructed django/.git boundary.
