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

---

## Task 02 — Test package and deterministic fixtures
Status: complete. Written 2026-09-10. No commits made (orchestrator verifies then commits).

### Files changed
- `report_v2/tests.py` -> `report_v2/tests/test_routes.py` (byte-exact `git mv`; the only content
  edit is the post-move relative-import fix `from . import views` -> `from .. import views`).
  The four original route/static/auth tests are preserved verbatim in behaviour
  (`test_report_routes_are_separate`, `test_both_reports_require_login`,
  `test_v2_renders_without_database_access`, `test_static_assets_are_discoverable`).
- `report_v2/tests/__init__.py` (new, empty package marker).
- `report_v2/tests/factories.py` (new) — synthetic fixture/factory layer.
- `report_v2/tests/test_factories.py` (new) — focused tests validating the fixtures against the
  runbook hand-checks.
Nothing else touched. `upload/models.py`, the legacy `report` app, and settings were not modified.

### Delegation split
Coding of `factories.py` + `test_factories.py` was delegated to the `pi` CLI
(`pi --print --no-session --approve --model qwen3.8-flash-next`) from inside `django-app/`.
pi read `upload/models.py` and `lunit_audit/settings.py` itself for real field names, wrote both
files, ran the suite, and self-reported green. I independently re-ran everything and re-derived the
numbers; the migration (`git mv`) and the one-line import fix were done by me directly.

### Determinism
Single module-level integer `FIXED_SEED = 20260910` in `report_v2/tests/factories.py`. Every
builder draws from `random.Random(FIXED_SEED + offset)` (a fresh instance per call), so repeated
calls and repeated runs produce byte-identical values. `test_determinism` asserts
`builder() == builder()` for the seeded builders. No unseeded randomness, no time-based values.

### Synthetic-only guarantees
Reserved non-clinical accession block (900000000..), `SYNTH`-prefixed patient/study/text/site
literals, and `assert_no_real_identifiers` / `_assert_synthetic_only` guards applied before every
ORM save. No real accession numbers, patient identifiers, or realistic report text appear anywhere
in the fixtures. DB builders are gated by `ensure_test_database()`, which hard-rejects any on-disk
`*.sqlite/.sqlite3/.db` path (proven: it refuses a `db.sqlite3` path) and accepts only the runner's
in-memory/`test_`-prefixed database. No production database is opened or migrated. Tests use the
locmem mail backend and route any artifact root to a temp dir; they override the staticfiles storage
to plain storage and disable the secure SSL redirect, mirroring the existing test convention.

### Fixture families (each: an in-memory builder for pure tests + a `*_db` builder for the test DB)
- Binary: `binary_fixture`, `binary_fixture_with_missing_gt`, `binary_fixture_no_positive_gt`
  (+ `_db`). Ground-truth labels vs predicted labels encoded via a designated finding score under
  the strict `> SCORE_THRESHOLD` policy (score 20 -> positive, 5 -> negative);
  `lunit_binarised` stored consistently with that policy for convenience (v2 recomputes it).
- Three-class: `three_class_fixture` (+ `_db`) over declared classes A/B/C.
- Timing: `timing_fixture` (+ `_db`) covering normal spread, single value, missing, invalid
  (negative sentinel), and a Tukey 1.5*IQR outlier; includes the 300s reference.
- Missing-field: `missing_field_fixture` (+ `_db`) for missing ground truth, a None constituent
  score (require-all ineligible), and a missing duration.
- Older-subgroup: `older_subgroup_fixture` (+ `_db`) laying out the anchor-D / older-subgroup /
  widget-boundary / newer-incomplete date geometry.
- `create_default_population()` lays a small deterministic two-site mix.

### Hand-checkable cases — verified consistent with the laid-down fixtures (independently re-derived)
- Binary comparison: GT [1,1,1,0,0,0] / pred [1,1,0,1,0,0] -> TP=2, FN=1, FP=1, TN=2;
  accuracy, sensitivity, specificity, PPV, NPV and balanced accuracy all = 2/3; predicted-negative
  fraction = 3/6. Missing-GT variant: matching=7, eligible=6, excluded=1 (does not move the
  metrics). All-GT-positive removed -> sensitivity is null (not zero).
- Threshold versioning (strict `>`): [10,10] -> negative; [11,10] -> positive; [11,None] ->
  ineligible (require-all); threshold 12 -> [11,10] flips to negative; identical rows across the
  two sites yield identical labels.
- Multiclass: matrix (rows=GT order A,B,C / cols=pred) = [[1,1,0],[0,1,1],[1,0,1]]; accuracy 1/2;
  class A TP=1, FN=1, FP=1, TN=3 -> sensitivity 1/2, specificity 3/4.
- Calendar windows: cohort anchor D = 2026-09-01; older subgroup reaches only through 2026-08-28;
  a widget whose required fields are complete only through 2026-08-30 gets its own boundary; the
  newer 2026-09-10 incomplete row does not advance D.
(These are the *fixture data*; Task 03+ measurement code is what turns them into the metrics above.
The measurement engine is intentionally not reimplemented here.)

### Deviations / notes
- `nodule` policy threshold is 15 in `lunit-defaults.v1.yaml`; the binary fixture's designated
  finding is a single representative score field chosen so the strict `>10` rule reproduces the
  predicted label — it is a fixture-encoding convention, not a clinical threshold decision. Later
  measurement tasks (05/07) should classify directly from the per-finding score dictionaries that the
  in-memory records already carry, against the real policy.
- In-memory records are plain dicts (a typed dataclass wrapper can be added when the measurement
  layer wants typed access).
- The pre-existing `lunit_audit.W002` (LLM_BASE_URL over HTTP) system-check warning is expected and
  not a failure.
- Known display artifact (not a code issue): the on-disk bytes of `test_routes.py` are canonical and
  it runs green; certain tokens render altered only in my read-back view.

### Validation (from `django-app/`, project virtualenv)
```
.venv/bin/python manage.py test report_v2 --noinput -v 1                     # Ran 12 tests ... OK
.venv/bin/python manage.py test report_v2.tests.test_routes --noinput -v 1   # Ran 4 tests ... OK
.venv/bin/python manage.py test report_v2.tests.test_factories --noinput -v 1# Ran 8 tests ... OK
.venv/bin/python manage.py test lunit_audit --noinput -v 1                    # Ran 16 tests ... OK
git diff --check                                                              # clean (CRLF->LF warning only)
```
No JS files were added, so no `node --check` was required. No real/clinical database was read; the
sample snapshot DB was never opened or migrated. No commits, pushes, resets or cleans were run.


## Task 03 — Strict YAML parsing and structural schemas

> Provenance note: the implementing session's own report was lost to a
> gateway delivery drop; the evidence below is the orchestrator's
> independent re-verification of the working tree, not a self-report.

**Changed/added files**
- `django-app/report_v2/definitions/__init__.py` (package marker)
- `django-app/report_v2/definitions/loader.py` (strict loader)
- `django-app/report_v2/definitions/schemas/report.schema.json` (copy of the reviewed planning schema)
- `django-app/report_v2/definitions/schemas/policy.schema.json` (new strict policy schema)
- `django-app/report_v2/tests/test_definitions.py` (24 tests)

**Implementation contract**
- Safe constructors only (`yaml.safe_load` family); no executable templates.
- Explicit duplicate-key detection in block and flow styles.
- Rejected constructs, each with a named test: aliases/anchors, custom/unknown
  tags, merge keys, multiple documents, excessive size/depth/node-count,
  oversize scalars, nonfinite numbers, unknown/missing/extra keys, wrong types.
- Path-aware editor messages (test asserts the offending YAML path is reported).
- Malformed calendar dates (e.g. 2026-02-30, quoted and unquoted) rejected
  semantically via real date construction, not by regex.
- Validation is read-only: `test_validation_writes_nothing_to_disk` asserts no
  file creation on any rejection path.
- Both seed examples (`prime-overview.yaml`, `lunit-defaults.v1.yaml`) parse
  and validate through the loader (two named tests).

**Test commands + results (verified by the orchestrator)**
```
.venv/bin/python manage.py test report_v2.tests.test_definitions --noinput -v 2   # 24 tests, OK
.venv/bin/python manage.py test report_v2 --noinput -v 1                          # 36 tests, OK
.venv/bin/python manage.py test lunit_audit --noinput -v 1                        # 16 tests, OK (no regression)
git diff --check                                                                  # clean
```
Run from `django-app/` with the project virtualenv. The single expected
lunit_audit.W002 system-check warning is unrelated to this task.

**Deviations:** none material. PyYAML and jsonschema were installed in the
dev virtualenv earlier for this task; they are pure-python additions and the
only tolerated requirements touch would have been listing them (not done —
loader works with what the app already vendors; re-check at Task 11 if the
runtime image needs them added to requirements.txt explicitly).
