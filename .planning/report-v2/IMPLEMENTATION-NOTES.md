# Task 01 Implementation Notes

Status: complete. Written 2026-09-10.

## Inventory scope

Read-only inspection of: report_v2 shell, upload/models.py, report/views.py,
report/static/report/charts.js, lunit_audit/settings.py, docker-compose.yml,
report_v2/tests.py, upload/context_processors.py, planning seed documents,
lunit-defaults.v1.yaml, prime-overview.yaml, report.schema.json, YAML-CONTRACT.md,
DESIGN.md, LEGACY-MAP.md.

No database contents inspected. No thresholds modified.

---

## Source field to implementation mapping

| CXRStudy field | Type | Used in legacy report (report/views.py) | Seed reference (prime-overview.yaml) | Notes |
|---|---|---|---|---|
| `accession_no` | BigInteger PK | CSV export, case detail | `accession` column | |
| `workplace` | Char(50) | site grouping, filter, CSV | `site` filter/comparison | |
| `procedure_start_date` | DateTime | date range filter, ordering | `window.start`/`end` | |
| `abnormal` | Float 0-100 | CSV export | *(not a seed input)* | |
| `atelectasis` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `calcification` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `cardiomegaly` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `consolidation` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `fibrosis` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `mediastinal_widening` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `nodule` | Float 0-100 | threshold(15), CSV, highest-finding | policy `findings` | Default 15 not 10 |
| `pleural_effusion` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `pneumoperitoneum` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `pneumothorax` | Float 0-100 | threshold, CSV, highest-finding | policy `findings` | |
| `tuberculosis` | Float 0-100 | CSV export | *(not in seed policy)* | No threshold policy entry |
| `gt_llm` | SmallInt 0/1 | ground truth in _compute_metrics | `llm_abnormal` | |
| `gt_manual` | SmallInt 0/1 | ground truth in _compute_manual_vs_llm | `manual_abnormal` | |
| `lunit_binarised` | SmallInt 0/1 | prediction in _compute_metrics | `lunit_findings` | |
| `llm_grade` | SmallInt 1-5 | CSV export | *(not a seed input)* | |
| `*_llm` (per-finding) | SmallInt 0/1 | CSV export | *(not in seed)* | Supplemental findings |
| `time_to_clinical_decision_seconds` | Float | _compute_time_stats | `time_to_clinical_decision` | |
| `time_end_to_end_seconds` | Float | _compute_time_stats | `time_end_to_end` | |
| `text_report` | Text | CSV, case detail | `report_text` column | |
| `patient_age`, `patient_gender` | Int/Char | *(unused in report)* | *(not in seed)* | |

### Score scale and operator (confirmed)

- Scale: 0..100 (floating point).
- Operator: `>` (strictly greater than). Source: `report/views.py:108` — `val > thresh`.
- Aggregate rule: any_positive (any finding above threshold makes the study positive).
- Completeness: all 10 configured finding scores must be present for a valid aggregate prediction
  (proposed v2 behaviour; legacy code does not enforce this — it skips None scores per-field).
- `lunit_binarised` is stored; v2 must recompute from original scores using the policy, not trust it.

### Cohort definitions

| Cohort ID (seed) | Implementation | CXRStudy condition |
|---|---|---|
| `manual_label_present` | Used by llm_lunit, manual_lunit, agreement, mcnemar, FN/FP widgets | `gt_manual IS NOT NULL` |

No other named cohorts are referenced in the seed.

### Derived output fields (from _compute_metrics / _compute_gt_metrics)

| Output key | Formula | Location |
|---|---|---|
| `n` | tp + tn + fp + fn | views.py:133 |
| `accuracy` | (tp+tn)/n | views.py:134 |
| `sensitivity` | tp/(tp+fn) or 0 | views.py:135 |
| `specificity` | tn/(tn+fp) or 0 | views.py:136 |
| `ppv` | tp/(tp+fp) or 0 | views.py:137 |
| `npv` | tn/(tn+fn) or 0 | views.py:138 |
| `roc_auc` | (sensitivity+specificity)/2 | views.py:139 — see discrepancy #1 |
| `pct_normal` | (tn+fn)/n * 100 | views.py:150 |

### Seed-to-code column mapping (classification_summary table columns)

| Seed column | Source |
|---|---|
| `n` | tp+tn+fp+fn |
| `accuracy` | (tp+tn)/n |
| `balanced_accuracy` | (sensitivity+specificity)/2 — see discrepancy #1 |
| `sensitivity` | tp/(tp+fn) |
| `specificity` | tn/(tn+fp) |
| `ppv` | tp/(tp+fp) |
| `npv` | tn/(tn+fn) |
| `tp`/`tn`/`fp`/`fn` | confusion counts |
| `predicted_negative_fraction` | (tn+fn)/n |

---

## Admin rule and access model (confirmed)

- Admin check: `user.is_superuser` OR `user.groups.filter(name='admins').exists()`.
  Source: `upload/context_processors.py:13-15`, duplicated in `upload/views.py` and `viewer/views.py`.
- Report routes require `@login_required`. Viewer and task routes require admin.
- report_v2 currently: `@login_required @require_GET` on the single `index` view.

### Mail/print behaviour (confirmed)

- Email: `email_report` view (POST) in `report/views.py:825-918`. Uses Django `EmailMessage`
  with configured SMTP backend. Tests must override to `locmem` backend.
- Print: `download_pdf` view (POST) in `report/views.py:923-949`. Renders a print-ready HTML
  via `render_to_string`. Browser handles Save-as-PDF. No PDF engine.

---

## Deployment volume relevant to report_v2

| Volume | Mount | Relevance |
|---|---|---|
| `django-db` | SQLite database | Reads CXRStudy rows |
| `django-media` | User uploads | Not used by report |
| `django-staticfiles` | Collected static | Serves report_v2 JS/CSS |
| `django-audit-artifacts` | Audit events/logs | Not used by report |
| *(none yet)* | `REPORT_DEFINITIONS_ROOT` | Task 11 will add a volume for published YAML |

The proposed `REPORT_DEFINITIONS_ROOT` path (per DESIGN.md:55-59) does not exist yet;
a new compose volume mount will be needed at Task 11.

---

## Fixture-safe test commands

```powershell
# Run from django/django-app after selecting the intended Python environment:
python manage.py test report_v2 --noinput
python manage.py test report_v2 lunit_audit --noinput

# After Task 02 splits tests into a package (anticipated):
python manage.py test report_v2.tests.test_routes --noinput
python manage.py test report_v2.tests.test_definitions --noinput

# Static syntax check (non-module JS):
node --check report_v2/static/report_v2/report.js
node --check report_v2/static/report_v2/vendor/echarts.min.js
```

- Tests must configure: `STORAGES` staticfiles to plain `StaticFilesStorage`,
  `SECURE_SSL_REDIRECT=False`, `EMAIL_BACKEND` to `locmem`.
- Tests must NOT access the production database; Django creates isolated test databases automatically.
- The known `lunit_audit.W002` LLM HTTP warning is informational; do not alter production transport settings.

---

## Legacy calculation discrepancies

### 1. Balanced accuracy mislabeled as ROC-AUC

**Location:** `report/views.py:139` (in `_compute_metrics`) and `report/views.py:368` (in `_compute_gt_metrics`).

**Issue:** The variable `roc_auc` is computed as `(sensitivity + specificity) / 2`, which is
*balanced accuracy* (macro-averaged recall). True ROC-AUC requires score-threshold sweep and
trapezoidal area computation (e.g. via scikit-learn `roc_auc_score`). The legacy label is misleading.

**Resolution for v2:** Relabel to `balanced_accuracy` throughout. The seed YAML already uses this
correct label. Do not introduce true ROC-AUC in this release; it requires a continuous score source
and a defined score-based AUC implementation which is out of scope per DESIGN.md:156-158.

**Impact:** All UI labels, table headers, email templates and chart titles that reference
"ROC-AUC" or "AUC" must be updated to "Balanced accuracy" when migrated to report_v2.

### 2. Inconsistent quartile/quantile methods between summary and box chart

**Location:** `report/views.py:185-224` (in `_compute_time_stats`).

**Issue:** The summary statistics text uses `statistics.quantiles(data, n=4)` (Python exclusive
interpolation, default `method='exclusive'`) for Q1/Q2/Q3, and `statistics.quantiles(data, n=20)`
for P5/P95. Meanwhile the legacy box chart in `charts.js` uses indexed quartile lookups with
`1.5 * IQR` clipped fences, producing whisker endpoints that differ from the server summary.

This causes visible inconsistency: the summary table may report a median or IQR value that does
not match the box chart geometry rendered client-side for the same dataset.

**Resolution for v2:** Use one standard quantile convention (proposed: Tukey hinges / inclusive
method) computed server-side. Send the complete box summary (min, Q1, median, Q3, max, whisker
low, whisker high, outlier list) to the renderer; do not let charts.js recompute from raw values.
Retain P5/P95 as separate text statistics. Record that v2 values may differ slightly from legacy.

---

## Operational timing vs diagnostic thresholds (separation note)

Timing measurements (`time_to_clinical_decision_seconds`, `time_end_to_end_seconds`) are stored
operational durations. They are independent of diagnostic score thresholds and threshold policy
versions. Changing a threshold policy version must never recalculate historical processing times.
The seed YAML correctly uses separate `duration_summary` measurements with `time_to_clinical_decision`
and `time_end_to_end` as value sources, distinct from classification measurements that reference
`lunit_findings` prediction with a threshold policy.

---

## No unknown fields

All CXRStudy fields are accounted for in the mapping table above. Fields not used by either the
legacy report or the seed YAML (`patient_name`, `patient_id`, `study_id`, `study_description`,
`instances`, `upload_date`, `inference_date`, `ai_report`, `ai_priority`, `ai_flag_received_date`,
`feedback`, `comments`, `status`, `procedure_end_date`, `medical_location_name`,
`study_id_anonymized`, `processing_batch_id`) are correctly absent from both implementations.

The `tuberculosis` score field exists in CXRStudy and CSV exports but has no threshold policy entry
in `lunit-defaults.v1.yaml` and no per-finding LLM binary (`tb_llm`) reference in the seed.
This is intentional per the existing default-threshold config (`report/views.py:34-50`), which
also excludes tuberculosis from the `DIAGNOSIS_FIELDS` list used for aggregate Lunit classification.
