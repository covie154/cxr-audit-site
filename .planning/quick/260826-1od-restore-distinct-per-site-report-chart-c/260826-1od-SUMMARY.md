---
quick_id: 260826-1od
status: complete
completed: 2026-08-26
implementation_commit: d82dbd7
description: Restore distinct per-site report chart colors from the initial palette
---

# Quick Task 260826-1od Summary

## Outcome

Restored the report's original categorical site-color sequence so individual
site lines are readily distinguishable in both light and dark themes.

## Delivered

- Replaced the visual-migration teal/slate sequence with the original blue,
  violet, amber, green, red, pink, cyan, lime, orange, and indigo palette.
- Preserved deterministic site indexing, chart labels, and all drawing behavior.

## Verification

- `node --check django-app/report/static/report/charts.js` passed.
- `python manage.py test lunit_audit`: 15 tests passed with the existing
  `lunit_audit.W002` private-HTTP endpoint warning.
- Confirmed the values match the pre-visual-migration implementation exactly.

