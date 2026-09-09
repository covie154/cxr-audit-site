---
gsd_type: quick-task
status: complete
created: 2026-09-10
task: report-v2 Task 01
depends: none
---

# Inventory and lock the implementation contract

Read-only inventory of the current report_v2 shell, upload models, legacy report logic, settings,
deployment volumes and test conventions. Produce IMPLEMENTATION-NOTES.md with an explicit mapping
table and two identified legacy calculation discrepancies.

## Acceptance

- Every seed source/cohort/output is mapped to its implementation code location.
- Two legacy discrepancies recorded: balanced-accuracy label and inconsistent quartiles.
- No unknown fields silently mapped.
- Operational timing definitions kept separate from diagnostic threshold changes.
- Fixture-safe test commands recorded.
