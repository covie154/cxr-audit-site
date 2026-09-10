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



## Task 04 (implementing session report)

Status: complete. Written 2026-09-10. All changes left UNCOMMITTED in the working
tree as untracked files for the orchestrator to stage and commit. No git-mutating
command was run. Depends on Task 03 (landed at 5f91418).

### Changed/added files (all NEW; no tracked file was modified)
- `django-app/report_v2/projects/__init__.py` — package marker re-exporting the
  base/prime/registry public surface (mirrors `definitions/__init__.py`).
- `django-app/report_v2/projects/base.py` — generic, project-agnostic frozen
  dataclasses: `Source`, `Outcome`, `Cohort`, `Dimension`, `ThresholdPolicy`
  (+`.ref` property), `MeasurementSignature`, `ProjectDefinition`; the closed
  vocabularies `KINDS`/`SOURCE_OPERATORS`/`AGGREGATES`; the `ProjectCatalogError`
  hierarchy including `UnknownProjectError`, `UnknownSourceError`,
  `UnknownOutcomeError`, `UnknownCohortError`, `UnknownDimensionError`,
  `UnknownPolicyError`, `UnknownMeasurementError`, `CrossProjectReferenceError`.
  Per-project strict lookups raise the typed errors; id/key integrity is checked at
  construction; `policy("id@version")` and bare-id resolution is strict (no default).
- `django-app/report_v2/projects/prime.py` — the single configured PRIME adapter
  catalog binding the generic structures to real `upload.CXRStudy` columns: 10
  `score_*` sources + record_id/site/procedure_date/report_text/manual_abnormal/
  llm_abnormal/lunit_binarised/time_* sources; three binary outcomes; cohorts
  `manual_label_present` (predicate `{"gt_manual__isnull": False}`) and `all`;
  the `site` dimension (SYNTH-SITE-A/B demo codes only); policy `lunit-defaults@1`
  (score_scale 0..100, operator gt, aggregate any_positive, require_all_scores,
  nodule 15 / others 10 — mirrors the read-only seed); the YAML-contract measurement
  signatures. `get_project_definition()` returns the frozen `PROJECT`.
- `django-app/report_v2/projects/registry.py` — `ProjectRegistry`; the thread-safe
  lazy `production_registry()` singleton (PRIME only, bootstrapped from `prime.PROJECT`);
  `register_production`; the single `require_project_context(...)` guard (NO default
  project, NO cross-project fallback — unknown project raises `UnknownProjectError`;
  an id that is missing locally but owned by exactly one OTHER registered project is
  escalated to `CrossProjectReferenceError`, otherwise the specific `Unknown*Error`
  re-raises); and a PHYSICALLY SEPARATE, documented TEST-ONLY path
  (`register_test_project`, `test_registry`, `require_test_project_context`) that
  reads/writes a distinct `_TEST_REGISTRY` singleton which `production_registry()`
  never imports, merges or falls back to.
- `django-app/report_v2/permissions.py` — reuses the house admin convention verbatim:
  `_is_admin(user) = user.is_superuser or user.groups.filter(name="admins").exists()`
  and `admin_required = user_passes_test(_is_admin)` (imported from
  `django.contrib.auth.decorators`, identical to upload/views.py + viewer/views.py).
  Plus `can_edit_catalog` (admin rule), `can_view_published` (authentication gate; the
  published-only *selection* is owned by the Task 11 repository layer), and the thin
  `published_report_only = login_required` convention decorator. No new permission
  model, group, or auth scheme.
- `django-app/report_v2/tests/test_catalog.py` — 24 hermetic `SimpleTestCase` tests
  with the standard staticfiles/SSL/locmem `override_settings` trio; a synthetic
  second project `synthx` built only from generic `x_*` metadata and registered via
  the test-only path / an explicit throwaway registry passed through the `registry=`
  kwarg (never the production singleton). No ORM/`upload.models` import, no DB access.

### Delegation split (pi) vs. orchestrator-authored
Coding of all six files was DELEGATED to `pi`
(`pi --print --no-session --model qwen3.8-flash-next`, run from inside the repo) via
a single self-contained, tightly-scoped prompt (/tmp/pi-task04-prompt.txt) that fixed
the exact file list, the generic/prime vocabulary-boundary rule, the frozen-dataclass
shapes, the PRIME facts (verified against `upload/models.py` and the seeds), the
require-guard semantics, and the test coverage matrix. pi wrote all six files and
self-reported green. The orchestrator (this session) independently:
- re-ran every validation command below against the venv and captured real output;
- independently `grep`-verified that base.py + loader.py contain ZERO clinical field
  tokens (exit 1 = no match) and that every real column string used by prime.py
  exists in `upload/models.py`;
- ran an additional adversarial `manage.py shell`-equivalent probe (/tmp/task04_probe.py,
  real Django settings, no DB) proving: the production registry resolves only `prime`
  even after test-registration of a synthetic project; case/whitespace lookalikes
  (`""`, `"PRIME"`, `"prime "`, `"Prime"`) do NOT resolve to PRIME; unknown-not-foreign
  ids stay the specific `Unknown*Error`; genuine foreign ids escalate to
  `CrossProjectReferenceError` naming both projects; the admin rule is superuser-or-admins only.
No substantive re-authoring of pi's code was required; the orchestrator added only
the independent verification harness. pi flagged two self-noted interpretations, both
accepted as correct: (1) this Django build's `user_passes_test` denies by 302-redirect
to login rather than raising, so the decorator-rejection test asserts the 302 + that
the protected body never runs (consistent with the existing test_routes.py convention);
(2) policy thresholds stored as floats compared against int literals with `==` (equal).

### Validation commands + real results (run from `django-app/`, project virtualenv)
```
$ .venv/bin/python manage.py test report_v2 --noinput -v 2
    ... Ran 60 tests in 0.160s ... OK      (36 pre-existing + 24 new test_catalog)
    Only the expected lunit_audit.W002 (LLM HTTP / DEBUG=False) warning.

$ .venv/bin/python manage.py test report_v2.tests.test_catalog --noinput -v 2
    Ran 24 tests in 0.016s ... OK
    "Skipping setup of unused database(s): audit, default."  (no DB contacted)

$ .venv/bin/python manage.py test lunit_audit --noinput -v 1
    Ran 16 tests in 0.404s ... OK          (16/16 baseline, no regression)
    Only the expected lunit_audit.W002 warning.

$ git diff --check
    clean (exit 0; no tracked modifications exist — every change is a new file)

$ grep -i -n '<CXR field tokens>' report_v2/projects/base.py report_v2/definitions/loader.py
    (no output)  grep exit 1  → CLEAN: generic model + parser free of clinical field names

$ python manage.py shell-equivalent probe (/tmp/task04_probe.py)
    ALL PROBE ASSERTIONS PASSED (production isolation, no-fallback, cross-project
    escalation, case/whitespace lookalikes, admin rule)
```
Before these additions the tree was green at 5f91418 (report_v2 36, lunit_audit 16),
re-confirmed here as report_v2 60 (incl. 24 new) and lunit_audit 16.

### Fixtures used
No new DB fixtures. `test_catalog.py` needs none of `factories.py` — it exercises
metadata + permission predicates with `Mock()` users (is_superuser + a mocked
groups.filter().exists() branch, mirroring test_routes.py) and a purely synthetic
`synthx` project whose identifiers are generic `x_*` tokens (no CXR field names, no
accessions, no clinical text). The PRIME catalog itself is metadata only and performs
no queries, so `@databases`/ORM is never used and the reserved-accession / SYNTH
conventions are not exercised (nothing writes rows). The sample snapshot DB
(`~/serverfiles/downloads/db_2026-06-18.sqlite3`) was NOT opened, read or migrated;
its mtime is unchanged.

### Where the guarantees live (audit pointers)
- Admin edit rule enforced in `report_v2/permissions.py` (`_is_admin` +
  `admin_required = user_passes_test(_is_admin)`), the verbatim duplicate of the
  pattern documented in AGENTS.md and present in upload/views.py + viewer/views.py.
- Authenticated-view rule in `permissions.can_view_published` + `published_report_only`
  (login gate); "published only" selection deferred to Task 11 repository, per DESIGN.md.
- Test-only second project unreachable from production navigation: production code reads
  ONLY `production_registry()` (a distinct singleton bootstrapped from `prime.PROJECT`);
  the `_TEST_REGISTRY` / `register_test_project` / `require_test_project_context` trio
  never feeds it. Proven by both `test_registering_test_project_never_touches_production`
  and the live probe (`production_registry().ids() == ("prime",)` after test registration).
- No CXR field names in generic parsing: proven by the grep (base.py + loader.py clean)
  and by `ParserPurityTests` asserting the forbidden-token set is absent from both
  module sources; the tokens appear only in the adapter `prime.py`, which is the
  sanctioned location.

### Deviations / blockers
- No blockers. No deviations from the Task 04 "Done when" checks: unknown project/source
  ids fail; referencing a foreign project's source from the PRIME context raises
  `CrossProjectReferenceError`; no CXR field names in generic parsing; NO project-
  membership models and NO migrations were added (none of settings.py, models.py,
  urls.py, views.py, definitions/loader.py were touched — confirmed by
  `git status --porcelain`).
- Forward-looking note for later tasks: the catalog currently stores mappings as plain
  `dict`s; the dataclass fields are frozen but the contained `Mapping` values are not
  recursively sealed (they are treated read-only by convention). `require_project_context`
  intentionally keeps the "exactly one clear foreign owner" heuristic (ambiguous shared
  ids stay `Unknown*Error` rather than risk a wrong cross-project accusation). Neither
  affects this task's acceptance.
- PyYAML/jsonschema (Task 03 devdeps) remain available in the venv; no new package was
  installed this task (pure-python/stdlib + Django only).


## Task 05 (implementing session report)

Status: complete. Written 2026-09-10. All changes left UNCOMMITTED in the working tree
for the orchestrator to stage and commit. No git-mutating command was run. Depends on
Task 04 (landed at f2f8b35). Baselines at start: report_v2 60/60, lunit_audit 16/16.

### Changed/added files (all NEW/untracked; no tracked file modified)
- `django-app/report_v2/measurements/__init__.py` — package marker re-exporting the
  predictions public surface (mirrors `definitions/__init__.py` style).
- `django-app/report_v2/measurements/predictions.py` — the pure implementation (437 lines).
  No Django/ORM/DB import at all; predictions are computed *values*, never stored labels;
  nothing touches `lunit_binarised` or any persisted column. Public API:
  `resolve_policy(project_id, policy_ref, *, registry=None)` (delegates to the Task-04
  `require_project_context(..., policy_ref=...)` guard then reads the policy back off the
  resolved `ProjectDefinition`, so unknown/foreign refs fail with the *typed* base errors
  — `UnknownPolicyError`/`CrossProjectReferenceError`/`UnknownProjectError` — unconverted,
  no fallback, no default version); `classify_prediction(findings, *, project_id, policy_ref,
  registry=None, outcome_id="abnormal_lunit")` -> `PredictionResult`; and
  `classify_label_prediction(label_value, *, project_id, outcome_id, registry=None)` ->
  `LabelPredictionResult`. Error hierarchy `PolicyEvaluationError` (+ `ScoreOutOfRangeError`,
  `NonFiniteScoreError`, `UncoveredFindingError`, `MissingPolicyError`,
  `InvalidPolicyConfigurationError`, `OutOfVocabularyLabelError`), mirroring the
  base/`kind`+message+__str__ shape. Frozen value objects `FindingDecision`,
  `PredictionResult`, `LabelPredictionResult` (+ `as_dict()`).
- `django-app/report_v2/tests/test_thresholds.py` — 20 hermetic `SimpleTestCase` tests
  with the standard staticfiles/SSL/locmem `override_settings` trio; a synthetic `handth`
  two-finding project built from the generic `base` dataclasses (thresholds 10 v1 / 12 v2),
  PRIME exercised via a throwaway registry and the read-only production path. No ORM, no
  `factories.py`, no `upload.models` import, no DB access.

### Delegation split (pi) vs orchestrator-authored
The coding was DELEGATED to `pi` (`pi --print --no-session --approve --model
qwen3.8-flash-next`, run from inside the repo) via one self-contained, tightly-scoped
prompt (/tmp/pi-task05-prompt.txt) that fixed the exact three-file list, the required
public API signatures, the exact 0..100 / finite / strict-gt / require-all semantics, the
coverage/one-default-per-finding validation order, the label-pass-through no-policy-lookup
rule, the typed-error propagation rule, and the full named-test matrix. pi authored all
three files and self-reported green (report_v2 80, lunit_audit 16). The orchestrator
(this session) independently, without editing any product file:
- re-ran every validation command below against the venv and captured real output;
- audited the implementation source line-by-line and every test body for real (non-tautological)
  assertions;
- wrote and ran an independent adversarial probe (/tmp/task05_probe.py) that drives the
  public API directly (independent of pi's tests) proving equality-at-threshold=negative,
  strict-gt boundary (10.0 neg vs 10.000001 pos), require-all missing -> eligible False +
  label None + positive None + reason names the constituent, v1/v2 coexistence with
  immutability snapshots, site-invariance, label pass-through on a policy-less project, every
  typed guard raising with no silent negative fallback, the full-ten PRIME production path,
  and module purity (no ORM/DB symbols) — ALL PROBE ASSERTIONS PASSED;
- wrote and ran a pure-Python semantics prototype (/tmp/proto_task05.py) of the intended
  classification before delegating, to fix expected hand-check values independently.
No re-authoring of pi's code was required. One accepted modelling nuance is recorded below.

### Validation commands + real results (run from `django-app/`, project virtualenv)
```
$ .venv/bin/python manage.py test report_v2.tests.test_thresholds --noinput -v 2
    Ran 20 tests in 0.004s ... OK      (all 20 named tests individually "ok"; no DB contacted:
    "Skipping setup of unused database(s): audit, default.")
$ .venv/bin/python manage.py test report_v2 --noinput -v 1
    Ran 80 tests in 0.164s ... OK      (60 pre-existing + 20 new test_thresholds)
$ .venv/bin/python manage.py test lunit_audit --noinput -v 1
    Ran 16 tests in 0.408s ... OK      (16/16 baseline, no regression)
$ git diff --check
    clean (exit 0; the only changes are two NEW untracked paths)
$ git status --porcelain
    ?? django-app/report_v2/measurements/
    ?? django-app/report_v2/tests/test_thresholds.py
$ git diff --name-only HEAD -- upload/models.py lunit_audit/settings.py report_v2/projects \
      report_v2/definitions report_v2/tests/factories.py
    (no output) => every forbidden/adjacent file is byte-identical to HEAD (untouched)
$ .venv/bin/python -m py_compile -q <the three files>
    exit 0 (all parse)
$ PYTHONPATH=. .venv/bin/python /tmp/task05_probe.py
    ALL PROBE ASSERTIONS PASSED
$ stat the sample snapshot DB (never opened/read/migrated): mtime unchanged 2026-06-18 22:51:24
```
The single expected `lunit_audit.W002` (LLM_BASE_URL over HTTP / DEBUG=False) system-check
warning is informational and unrelated. Repeated runs are deterministic (fixed 20/80/16).

### Five hand-checkable cases (runbook "Threshold versioning" block) — exact values
Policy thresholds 10, strict gt, two findings {consolidation, nodule}, require_all=True,
outcome classes ("normal","abnormal"), positive "abnormal":
- `[10,10]` -> NEGATIVE. eligible True, positive False, label "normal"; each per-finding
  decision.positive False (10 is NOT > 10). Asserted by
  `test_score_equal_to_threshold_is_negative` (also in `test_hand_check_threshold_block`).
- `[11,10]` -> POSITIVE. eligible True, positive True, label "abnormal"; consolidations
  decision.positive True (11>10), nodule False (10 !> 10). Asserted by
  `test_score_above_threshold_is_positive`.
- `[11,null]` -> INELIGIBLE (require-all). eligible False, label None, positive None,
  missing_findings ("nodule",), result.reason literally names "nodule" ("ineligible under
  require-all policy: missing constituent score(s): nodule"). Never defaulted to the
  negative label. Asserted by
  `test_missing_constituent_makes_aggregate_ineligible_not_negative`.
- version 2 (threshold 12) turns `[11,10]` -> NEGATIVE. positive False, label "normal"
  (11 !> 12). Asserted by `test_policy_version_one_and_two_coexist_without_overwrite` and
  `test_hand_check_threshold_block`.
- identical rows assigned to two synthetic sites keep EQUAL labels. Asserted by
  `test_identical_scores_across_two_sites_produce_identical_labels`.

### Where each guarantee is asserted (test names)
- equality-at-threshold negative -> `test_score_equal_to_threshold_is_negative`,
  `test_gt_is_strict_not_ge` (10.0 neg, 10.000001 pos), `test_primes_policy_resolves_from_production_registry`
  (the all-5.0 baseline is negative and atelectasis 10 !> 10; the independent probe additionally
  checked nodule 15 !> 15, i.e. equality at the 15 threshold).
- strict gt / above-threshold positive -> `test_score_above_threshold_is_positive`,
  `test_gt_is_strict_not_ge`, `test_primes_policy_resolves_from_production_registry`
  (nodule 20>15, atelectasis 11>10).
- require-all ineligibility (eligible=False + reason, never negative) ->
  `test_missing_constituent_makes_aggregate_ineligible_not_negative`,
  `test_primes_missing_any_of_ten_findings_is_ineligible`.
- site-invariance -> `test_identical_scores_across_two_sites_produce_identical_labels`.
- policy-version immutability + versioning (coexist, differ, no overwrite, no stored-label
  change) -> `test_policy_version_one_and_two_coexist_without_overwrite` (snapshots both
  policy.findings maps before/after, re-resolves v1 to threshold 10, asserts version attrs 1
  vs 2) and `test_pure_computation_no_orm_no_mutation`.
- typed-error resolution, no fallback -> `test_unknown_policy_raises_typed_error_no_fallback`,
  `test_foreign_policy_raises_cross_project_error`, `test_unknown_project_raises`.
- input validation (out-of-range / nonfinite / uncovered / bool / out-of-vocabulary) ->
  `test_out_of_range_score_rejected`, `test_nonfinite_score_rejected`,
  `test_uncovered_finding_rejected`, `test_bool_is_not_accepted_as_score`,
  `test_out_of_vocabulary_label_rejected`.
- label-valued sources pass through without thresholding / no policy lookup ->
  `test_label_passthrough_no_thresholding` (asserts a label result carries no `policy_ref`
  and that a policy-less project still classifies), `test_label_passthrough_missing_value`.
- predictions are computed values, not stored labels -> `test_pure_computation_no_orm_no_mutation`.

### How a missing constituent yields eligible=False with a stated reason (not a silent negative)
In `classify_prediction`, after per-finding binarisation a `None`/absent score is recorded as
a `FindingDecision(score=None, positive=None)` and its id lands in `missing_findings`. When
`policy.require_all_scores` is set (it is, for the shipped `lunit-defaults@1` and the
hand-check policy) and `missing_findings` is non-empty, the function returns
`PredictionResult(eligible=False, label=None, positive=None, reason="ineligible under
require-all policy: missing constituent score(s): <sorted, comma-joined missing ids>")`. The
negative class is only ever chosen on the fully-complete `else` branch, so a missing
constituent can never be coerced into the negative label. Proven by the two named tests above
and by the independent probe.

### Deviations / blockers
- No blockers. All "Done when" checks pass with named tests and an independent probe.
- One accepted modelling nuance: `base.ProjectDefinition.policies` is keyed by `policy_id` and
  stores exactly one `ThresholdPolicy` per key, and `policy("id@version")` validates
  `policy.version == version`. To make version 1 and version 2 *coexist* in one synthetic
  project without one overwriting the other, they are registered as two distinct immutable
  entries — `hand-thresholds@1` (thresholds 10) and `hand-thresholds-v2@2` (thresholds 12) —
  rather than two rows sharing a single key. This faithfully demonstrates immutability +
  versioning (distinct keys, differing `version` attrs, neither findings map mutates, the two
  produce different results on `[11,10]`, no stored label touched) and is documented in the
  test docstring. The production `lunit-defaults@1` policy is exercised unchanged through the
  real `production_registry()`.
- The suite needs no `factories.py` and touches no DB: `classify_prediction` reads
  `policy.findings` (not the ORM/source declarations) over a plain findings Mapping, so every
  test is pure `SimpleTestCase`. The reserved-accession / SYNTH conventions are therefore not
  exercised (nothing writes rows); the sample snapshot DB
  (`~/serverfiles/downloads/db_2026-06-18.sqlite3`) was NOT opened, read or migrated (mtime
  unchanged). No `upload/models.py`, no `CXrStudy` field, no `lunit_binarised`, no legacy
  report code, no settings/urls/views/migrations were modified (verified by `git diff --name-only
  HEAD` showing no diff). No new package was installed.


## Task 07 (implementing session report)

Status: complete. Written 2026-09-10. All changes left UNCOMMITTED in the working tree
for the orchestrator to stage and commit. No git-mutating command was run by this session
(only read-only `git status` / `git diff` / `git log`). Depends on Task 05 (landed at
b6386f9). Baselines at start: report_v2 117/117, lunit_audit 16/16 (both re-confirmed
green before any edit was made).

### Changed/added files (exactly three; nothing else in the repo was touched)
- `django-app/report_v2/measurements/classification.py` — NEW, 935 lines, the pure
  classification-measurement module. NO web-framework import, NO ORM import, no DB/file/network
  access: it receives already-extracted row *values*. Public surface (in `__all__`):
  `ClassificationError` + `OutOfVocabularyClassError` / `MissingTargetClassError` /
  `InvalidClassOrderError` / `IncompatiblePairError` / `EmptyPopulationError` (mirroring the
  `base`/`predictions` `kind`+`message`+`__str__` shape); `BALANCED_ACCURACY_LABEL =
  "Balanced accuracy"`; `BinaryClassVocabulary` + `vocabulary_from_outcome`;
  `pairs_from_rows`; `BinaryConfusionCounts` + `binary_confusion_counts`; `Rate` +
  `safe_rate`; `BinaryClassificationMetrics` + `binary_classification_metrics`;
  `ConfusionMatrix` + `confusion_matrix`; `TargetClassMetrics` + `one_vs_rest_metrics`;
  `require_target_class`; `ClassificationSummary` + `classification_summary`.
  Three private error subclasses (`_InvalidRateOperandError`, `_InvalidVocabularyError`,
  `_InvalidSummaryRequestError`) carry the spec-mandated `kind` discriminators
  `invalid-rate-operand` / `invalid-vocabulary` / `invalid-summary-request` and are
  deliberately underscore-prefixed and out of `__all__`.
  Single-source-of-truth structure: `safe_rate` is the ONLY gate that builds a `Rate`;
  `_matrix` is the ONLY NxN counter (used by `confusion_matrix`, `one_vs_rest_metrics` and
  `classification_summary`); `binary_classification_metrics` derives every one of the seven
  rates from `binary_confusion_counts`' cells alone; `classification_summary` contains NO
  independent arithmetic — it is a thin composition (binary path reads its counts/rates off
  `binary_classification_metrics`; multiclass path validates the target first, then reads the
  shared `_matrix` and `one_vs_rest_metrics`). Balanced accuracy is averaged over exact
  `Fraction`s taken from the two component rates' stored numerator/denominator, so `2/3` stays
  exactly `2/3`, and it is undefined (never `0`) whenever either component is undefined.
- `django-app/report_v2/tests/test_classification.py` — NEW, 38 hermetic `SimpleTestCase`
  tests in six named classes (`BinaryHandCheckTests`, `ZeroDenominatorNullTests`,
  `MulticlassMatrixTests`, `ValidationGuardTests`, `NamingAndScopeTests`,
  `ReuseAndPurityTests`), carrying the standard staticfiles/SSL/locmem
  `override_settings` trio. Reuses the Task-02 in-memory fixtures `binary_fixture`,
  `binary_fixture_with_missing_gt`, `binary_fixture_no_positive_gt`,
  `three_class_fixture` (lifted via `pairs_from_rows` on the real keys
  `gt_label`/`pred_label` and `gt_class`/`pred_class`). No ORM, no `*_db` builders, no DB
  access at all (the isolated run creates and destroys NO database — a strictly stronger
  DB-free signal than the `Skipping setup of unused database(s)` line).
- `django-app/report_v2/measurements/__init__.py` — EDITED (re-exports only, the established
  package-marker pattern): all 13 pre-existing predictions exports preserved verbatim, plus
  the 24 new classification names and an updated module docstring. `len(__all__)` is now 38.

### Delegation split (pi) vs orchestrator-authored
The coding of all three files was DELEGATED to `pi` (`pi --print --no-session --approve
--model qwen3.8-flash-next`, run from inside the repo) through ONE self-contained,
tightly-scoped prompt (`/tmp/pi-task07-prompt.txt`, ~38 KB) that fixed the exact three-file
list and forbidden paths, the required public API with field-by-field semantics, the
null-plus-reason contract, the stable-declared-order matrix rule, the required-explicit-
`target_class` rule and its validation-before-counting ordering, the bool-is-not-a-class rule,
the enforceable no-score-ranking naming scan rules, the eight DONE-WHEN clauses with their
named-test mapping, the hand-check ground truth, and the exact verification commands. pi
authored all three files and self-reported green (38 / 155 / 16).

The orchestrator (this session) independently, WITHOUT editing any product file:
- re-ran all three verification suites against the venv and captured real output (twice;
  the counts are stable across runs);
- wrote and ran a pure-Python oracle BEFORE delegating (`/tmp/proto_task07.py`) to fix the
  expected hand-check values independently of pi; it reproduced the runbook numbers exactly;
- audited pi's implementation line-by-line and every test body for real (non-tautological)
  assertions — all 38 assert exact numerators/denominators, typed `kind` values, message
  content, permutation geometry or JSON round-trips;
- wrote and ran an independent adversarial probe (`/tmp/task07_probe.py`) that drives the
  PUBLIC API directly, independent of pi's own test file: **135 checks, ALL PROBE ASSERTIONS
  PASSED**. It additionally proves things pi's suite does not: the group-denominator form of
  accuracy, that the balanced accuracy is the exact `(sens+spec)/2` rational, an
  all-excluded population (`matching 3 / eligible 0 / exclusions 3`, every rate null with a
  reason), disjoint-then-precedence attribution of `missing_ground_truth` over
  `missing_prediction`, a genuinely ASYMMETRIC declared-order permutation proof (a symmetric
  example cannot distinguish a correct implementation from a data-encounter-order one), that a
  first-seen class value does not decide row 0, order-invariance of the diagonal,
  `cell()` indexing by class rather than by position, JSON serialisability of every value
  object, non-mutation and determinism of repeated calls, the full exclusion/purity token
  scan of the on-disk bytes, and `pairs_from_rows` `None` preservation.

Two probe-side defects were found and fixed during that audit; BOTH were mine, not pi's (a
list-vs-tuple comparison on `pairs_from_rows`, and one hand-computed expectation for the
reversed-order matrix), and fixing them produced no change to any product file.

### Validation commands + real results (run from `django-app/`, project virtualenv)
```
$ .venv/bin/python manage.py test report_v2.tests.test_classification --noinput -v 2
    Found 38 test(s).  Ran 38 tests in 0.012s  OK        (all 38 individually "... ok")
    no database created/destroyed — zero DB lifecycle; "Skipping setup of unused database(s): audit, default."

$ .venv/bin/python manage.py test report_v2 --noinput -v 1
    Found 155 test(s).  Ran 155 tests in 0.211s  OK      (117 pre-existing + 38 new)

$ .venv/bin/python manage.py test lunit_audit --noinput -v 1
    Found 16 test(s).  Ran 16 tests in 0.407s  OK         (16/16 baseline, no regression)

$ git diff --check
    clean (exit 0)

$ git status --porcelain
    M  django-app/report_v2/measurements/__init__.py
    ?? django-app/report_v2/measurements/classification.py
    ?? django-app/report_v2/tests/test_classification.py

$ git diff --name-only HEAD -- upload/models.py lunit_audit/settings.py report/ \
      report_v2/projects report_v2/definitions report_v2/tests/factories.py \
      report_v2/measurements/predictions.py report_v2/dates.py
    (no output) => every forbidden/adjacent path is byte-identical to HEAD

$ .venv/bin/python -m py_compile -q <the three files>       -> exit 0
$ PYTHONPATH=. .venv/bin/python /tmp/task07_probe.py        -> ALL PROBE ASSERTIONS PASSED (135 checks)
$ .venv/bin/python /tmp/proto_task07.py                     -> oracle reproduces the runbook values
$ stat the sample snapshot DB (never opened/read/migrated): mtime unchanged 2026-06-18 22:51:24
```
Repeated runs are deterministic (fixed 38 / 155 / 16). The single expected
`lunit_audit.W002` (LLM_BASE_URL over HTTP / DEBUG=False) system-check warning is
informational and unrelated to this task.

### Hand-check values actually observed (from the live implementation, not from the docs)
Binary block — `binary_fixture()`, vocabulary `BinaryClassVocabulary(1, 0)`:
`TP=2, FN=1, FP=1, TN=2`; `eligible(matching)=6`, `exclusions=0`;
`accuracy 4/6`, `sensitivity 2/3`, `specificity 2/3`, `PPV 2/3`, `NPV 2/3`,
`balanced_accuracy 2/3` (label exactly `"Balanced accuracy"`) — all six `value ~= 2/3`;
`predicted_negative_fraction 3/6` and its denominator equals the group `n` (`eligible`),
while sensitivity's denominator (`tp+fn = 3`) is distinct from it.
Missing-GT variant: `matching=7, eligible=6, exclusions=1`,
`excluded == {"missing_ground_truth": 1}`, and all four cells + all seven rates are
byte-identical to the six-row case (`as_dict()` equality asserted).
No-positive-GT variant (`binary_fixture_no_positive_gt()`): `counts 0/0/3/3`;
`sensitivity.value is None` with a stated reason naming sensitivity and its zero
denominator, operands `0/0`, and `value is not 0` / `repr(value) != "0"`;
`balanced_accuracy` also `None` (its reason names the undefined component);
`PPV` is a **legitimate** `0.0` over denominator `3` with `null_reason is None` — proving
the module distinguishes a real zero from an undefined rate; group `n = 6` stays distinct
from `positive_cases = 0`, and accuracy keeps the group denominator `6`.

Multiclass block — declared order `("A","B","C")`, `three_class_fixture()`:
`cells == ((1,1,0),(0,1,1),(1,0,1))`, `rows_are="ground_truth"`,
`columns_are="prediction"`, `n=6`, `row_totals == column_totals == (2,2,2)`,
`accuracy 3/6 == 0.5`; class `A`: `TP=1, FN=1, FP=1, TN=3`, `sensitivity 1/2`,
`specificity 3/4`, `PPV 1/2`, `NPV 3/4`. A shuffled declared order
`("A","C","B")` yields the correspondingly permuted
`((1,0,1),(1,1,0),(0,1,1))`, and the probe's asymmetric case
`[("A","B"),("A","B"),("B","A"),("C","C")]` gives `(A,B,C) -> ((0,2,0),(1,0,0),(0,0,1))`
vs `(C,B,A) -> ((1,0,0),(0,0,1),(0,2,0))` — the geometry follows the DECLARATION, not
the order rows arrive in.

### Where each DONE-WHEN guarantee is asserted (test names)
- binary hand-check reproduces exactly -> `test_hand_check_binary_block_reproduces_exactly`
  (+ `test_predicted_negative_fraction_uses_the_group_denominator`,
  `test_missing_ground_truth_row_is_excluded_and_does_not_move_the_metrics`,
  `test_exclusion_reason_counts_are_non_overlapping_and_reconcile`)
- removing all GT positives makes sensitivity NULL with a reason, not 0, and keeps the
  positive-case denominator distinct from the group count ->
  `test_removing_all_gt_positives_makes_sensitivity_null_not_zero`,
  `test_positive_case_denominator_is_kept_distinct_from_the_group_count`
- zero denominators never become 0 estimates (table-driven over six populations, plus the
  `safe_rate(0,0)` vs `safe_rate(0,5)` distinction and operand validation) ->
  `test_zero_denominator_never_becomes_a_zero_estimate`,
  `test_safe_rate_rejects_invalid_operands`,
  `test_matrix_without_any_eligible_pair_has_null_accuracy`
- multiclass matrix / accuracy / class-A one-vs-rest ->
  `test_hand_check_multiclass_block_reproduces_exactly`,
  `test_target_class_one_vs_rest_rates_for_class_a`,
  `test_cell_lookups_follow_declared_geometry`,
  `test_declared_class_order_is_stable_and_not_data_encounter_order`
- a multiclass rate requested WITHOUT `target_class` fails validation (missing required
  kwarg -> `TypeError`; aggregate entry point / `None` / `""` / `"   "` ->
  `MissingTargetClassError` whose message forbids averaging; and the guard fires BEFORE any
  counting even when an out-of-vocabulary value is present) ->
  `test_multiclass_rate_without_target_class_fails_validation`,
  `test_missing_target_class_validation_precedes_counting`,
  `test_require_target_class_helper`,
  `test_no_unqualified_multiclass_sensitivity_is_exposed`
- out-of-vocabulary classes rejected with a typed error naming value/side/vocabulary (plus
  bool-is-not-a-class, malformed class orders, malformed pair containers) ->
  `test_matrix_rejects_out_of_vocabulary_classes`,
  `test_binary_rejects_out_of_vocabulary_labels`,
  `test_bool_is_not_silently_accepted_as_a_binary_class`,
  `test_invalid_class_order_rejected`,
  `test_incompatible_pair_containers_rejected`, `test_empty_population_raises_typed_error`
- balanced accuracy is labelled balanced accuracy and is NOT named for a score-ranking
  statistic anywhere; no cross-class averaging introduced ->
  `test_balanced_accuracy_is_labelled_balanced_accuracy_and_never_roc_auc`
  (label equality + recursive key walk over `as_dict()` + module-source scan +
  `dir()` + dataclass field-name scan),
  `test_no_roc_auc_or_cross_class_averaging_api_is_introduced` (forbidden-token set over
  `dir()`; no public `average`-named callable),
  `test_balanced_accuracy_is_the_mean_of_sensitivity_and_specificity` (exact `Fraction`
  equality — pins the definition WITHOUT naming it after a ranking statistic)
- purity / no divergent second implementation ->
  `test_no_module_level_django_or_orm_import`,
  `test_classification_summary_uses_the_same_primitives`,
  `test_metrics_are_pure_and_inputs_not_mutated`, `test_as_dict_is_json_serialisable`,
  `test_rate_accessor_rejects_unknown_metric`

### Deviations / notes
- **No blockers, and no validation was weakened to obtain green.** Every guard raises.
- One deliberate representativeness choice, accepted as correct and arguably preferable: the
  `accuracy` Rate carries the honest operands `(tp+tn)/n` (`4/6`) rather than a pre-reduced
  `2/3`, so the group denominator stays visible and the documented `(tp+tn)/n` formula is
  literally reflected; `value` is still exactly `2/3`, and every other rate carries its
  natural operands. This is asserted explicitly in
  `test_hand_check_binary_block_reproduces_exactly` and in the probe.
- `confusion_matrix`/`one_vs_rest_metrics` reject an entirely EMPTY input with
  `EmptyPopulationError`, which is kept distinct from "rows present but all excluded"
  (`eligible == 0`, rates null with reasons) — a documented design decision beyond the literal
  spec wording; the all-excluded path is what the null-rate contract governs, and it is
  covered. If a later task wants an empty population to yield an all-null summary rather than
  a typed error, that is a one-line change in `_validate_pairs_container` (flagged for the
  Task 08/13 authors, not applied here).
- The scan for the frozen no-score-ranking decision is deliberately asymmetric (plain
  substring for `auc`, word-boundary regex for a standalone `roc`) because ordinary English
  words such as "process"/"procedure" contain the three letters `roc`; a naive substring scan
  on `roc` would be an unsatisfiable trap. Both directions are asserted, and the module's
  prose avoids the two words entirely (it says "score-based ranking metrics are out of
  scope").
- No new models, migrations, packages, dependencies, fixtures or test files; no settings /
  urls / views / legacy `report/` / `upload/models.py` change; no deploy, no email, no
  network. The sample snapshot DB `~/serverfiles/downloads/db_2026-06-18.sqlite3` was NOT
  opened, read or migrated (mtime unchanged). The three suites use the locmem mail backend and
  the runner's isolated in-memory test databases only.

[TASK-07 COMPLETE]
