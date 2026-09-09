---
status: complete
---
# Report v2 Task 01: inventory and lock the implementation contract

Commit: bc2c5a7. Read-only inventory of the report_v2 shell, `upload/models.py` CXRStudy fields,
legacy `report/views.py`, `report/static/report/charts.js`, `lunit_audit/settings.py`,
`docker-compose.yml`, `report_v2/tests.py` and the report-v2 planning seed documents. Wrote
`.planning/report-v2/IMPLEMENTATION-NOTES.md`. No production code, thresholds or database contents changed.

The notes map every seed source, cohort and derived output to its implementation location, confirm the
0..100 score scale and strict `>` operator (`report/views.py:108`), the `any_positive` aggregate rule and
the require-all completeness rule v2 must add, and record the admin rule (`is_superuser` or `admins` group),
login-only report routes, SMTP email and browser print/PDF behaviour. They list fixture-safe test commands and
confirm `python manage.py test report_v2 --noinput` runs green (4 tests, only the informational
`lunit_audit.W002` HTTP-LLM warning).

Two legacy discrepancies are locked for correction in later tasks: (1) `roc_auc` is actually balanced accuracy,
computed `(sensitivity+specificity)/2` at `report/views.py:139` and `:368`; v2 relabels to `balanced_accuracy`
and does not introduce true score-based ROC-AUC. (2) Server `_compute_time_stats` uses `statistics.quantiles`
(n=4/n=20) while `charts.js` recomputes Tukey 1.5*IQR fences client-side, so summary and box geometry diverge;
v2 computes one convention server-side and ships the full box summary. Operational timing measurements are kept
separate from diagnostic threshold policy versions. No unknown CXRStudy field was silently mapped; `tuberculosis`
is intentionally outside the aggregate Lunit classification fields.

No clinical records read, no production code changed, no email sent, no deployment performed.
