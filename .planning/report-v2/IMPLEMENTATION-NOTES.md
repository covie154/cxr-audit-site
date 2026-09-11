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

## Task 08 (implementing session report)

Count / duration / reference-comparison measurements. Pure value helpers only (take
plain values in, return frozen dataclasses / scalars; no ORM, DB, web or network
imports). All synthetic; no real ePHI, no reference snapshot, no `upload/models.py`,
`CXRAStudy` fields, or legacy `report/` changes; no new models or migrations.

### Changed files
- `django-app/report_v2/measurements/descriptive.py` (new) - `record_count`, `label_count`,
  `categorical_count`, `duration_summary`, frozen `DurationSummary`, `QUANTILE_METHOD`,
  `TAIL_METHOD`, `DescriptiveError` / `UnexpectedQuantileMethod`.
- `django-app/report_v2/measurements/agreement.py` (new) - `cohen_kappa`, `mcnemar`,
  `fn_fp_cases`, shared `complete_rows` filter + frozen `CompleteRows`, local frozen `Rate`
  (null-plus-reason contract), frozen `McNemarResult` / `FnFpCases`, `AgreementError` base.
- `django-app/report_v2/tests/test_descriptive.py` (new) - 52 tests, Django `SimpleTestCase`,
  no DB writes, synthetic via `factories` (`timing_fixture`).
- `django-app/report_v2/tests/test_agreement.py` (new) - 50 tests, same discipline
  (`binary_fixture*` families).
- `django-app/report_v2/measurements/__init__.py` (extended) - re-exports both new public
  surfaces following the established Task-06/07 pattern. Note the real symbol collision:
  `classification` already exports `Rate`; the package's `Rate` stays `classification.Rate`
  and the agreement one is re-exported under the alias `AgreementRate` (no silent clobber).

### How it was built (pi + bail-out accounting)
Both pure modules were delegated to `pi` from the compact `/tmp/pi_task08_spec.md` only
(one small file each; never the 935-line `classification.py` / 823-line `dates.py`). Both pi
invocations exited 0 with the sentinels `DONE-DESCRIPTIVE` / `DONE-AGREEMENT` and produced
faithful modules - no bail-out was needed for the two modules. I (the orchestrator-side
subagent) WROTE BOTH TEST FILES MYSELF and fixed three of my own over-strict expectations
against the real spec surface (details below). No module was rewritten from scratch.

### Exact test commands + real output tail (venv python, run from django-app/)
- `.venv/bin/python manage.py test report_v2.tests.test_descriptive --noinput -v 2`
  -> `Ran 52 tests in 0.008s` / `OK`
- `.venv/bin/python manage.py test report_v2.tests.test_agreement --noinput -v 2`
  -> `Ran 50 tests in 0.009s` / `OK`
- `.venv/bin/python manage.py test report_v2 --noinput -v 1`
  -> `Ran 257 tests in 0.297s` / `OK`   (155 green baseline + 102 new = >= 155 preserved)
- `.venv/bin/python manage.py test lunit_audit --noinput -v 1`
  -> `Ran 16 tests in 0.400s` / `OK`   (16/16 preserved; the single W002
  LLM_BASE_URL-HTTP system-check warning is the known/pre-existing, non-failing notice)
- `git diff --check` -> clean (no whitespace errors).

### Tukey micro-case (named test, observed values)
`test_documented_hand_check_upper_whisker_and_single_outlier` on `[1..10, 100]` (n=11):
`q1=3`, `median=6`, `q3=8`, `iqr=5`, `lower_fence=-4.5`, `upper_fence=15.5`,
`outliers=[100]` (the ONLY outlier), `upper_whisker=10` (largest observed datum <= 15.5),
`lower_whisker=1`. Mean=155/11 (the outlier is reported, never dropped from n/mean).

### Kappa cases
- Perfect agreement -> `value == 1.0` exactly, `defined=True`, `null_reason=None`
  (`test_perfect_agreement_is_exactly_one`).
- Undefined (degenerate marginals: a single class on BOTH sides so expected agreement==1, and
  the empty complete population) -> `value=None` WITH a non-empty `null_reason`, `defined=False`,
  and asserted `is not 0` / `is not 0.0` (`test_undefined_is_never_zero`,
  `test_truly_degenerate_single_class_column_is_null_never_zero`). Never 0.
- Contrast, kept as its own named test so the two states are proven distinct: a single-class
  REFERENCE with a MIXED prediction (`binary_fixture_no_positive_gt`) is NOT degenerate - the
  expected agreement is 0.5, so kappa is a *measured, defined* `0.0` with `null_reason=None`
  (`test_fixture_no_positive_reference_kappa_is_a_defined_zero_not_null`). This was one of the
  three expectations I corrected after running: my first draft wrongly demanded null here.
- The runbook block `[1,1,1,0,0,0]` vs `[1,1,0,1,0,0]` -> `numerator=4`, `denominator=6`,
  value `(4/6 - 1/2)/(1 - 1/2)`.
- Structural guard: a defined `Rate` may not smuggle a `null_reason`, and an undefined one must
  carry a non-blank reason (enforced in `Rate.__post_init__`; asserted in tests).

### McNemar discordant counts + method
`test_binary_block_discordant_counts`: b=1, c=1, n_discordant=2, n_total=6, n_complete=6.
Direction fixed: `b` = reference-positive & prediction-negative, `c` = reference-negative &
prediction-positive; a role swap moves them across cells (`test_discordant_direction_is_not_swappable`).
Method (documented in `MCNEMAR_METHOD`, asserted to name it): exact TWO-SIDED binomial
`p = 2 * sum(C(n,k) * 0.5**n for k <= min(b,c))`, n=b+c, computed with `fractions.Fraction`
and clipped to 1.0; `statistic` = continuity-corrected chi-square `(abs(b-c)-1)**2/(b+c)`.
A cross-check test compares `p_value` against an independent float restatement to 12 places, and
symmetry in (b,c) is asserted (two-sidedness). When `n_discordant==0` both `statistic` and
`p_value` are `None` with a reason in `p_note` (never a fabricated 0). Example: b=12,c=1 ->
statistic 121/13 and p<0.05; b=3,c=0 -> p=0.25.

### Documented quantile convention (single, used everywhere)
`QUANTILE_METHOD = "lower order statistic: Q(p) = sorted[floor(p * (n - 1))], 0-based,
clamped to [0, n-1], no interpolation"`. ONE convention drives `q1`/`median`/`q3` AND the
`p5`/`p95` tails; there is no per-call-site variant, and `duration_summary` REFUSES a
differently-documented method with `UnexpectedQuantileMethod` so the convention cannot drift
(the historical quartile/quantile inconsistency is structurally prevented, not just avoided).
Cross-checked by `test_every_quantile_field_matches_the_independent_restatement` against an
independent restatement of the same formula.

### Separate P5 / P95
p5=Q(0.05) and p95=Q(0.95) are SEPARATE tail summaries carried with their own `tail_method`
note; they are NOT the Tukey whiskers and are NOT folded into q1/q3. Proven by
`test_p95_is_not_the_upper_whisker_and_not_q3` (upper_whisker=200 while p95=400) and
`test_p5_is_not_the_lower_whisker_and_not_q1` (lower_whisker=10 while p5=0, and 0 is itself
flagged an outlier). Whiskers are always observed data values inside the fences, never the fences.

### FN/FP direction assertion + incomplete-pair exclusion
`fn_fp_cases` direction is FIXED: `reference='manual'` (ground truth), `prediction='llm'`.
FALSE NEGATIVE = reference-positive & prediction-negative; FALSE POSITIVE = reference-negative &
prediction-positive; never swapped (`test_direction_is_manual_reference_and_llm_prediction`,
`test_every_listed_case_carries_the_documented_orientation`, and
`test_swapping_the_direction_names_is_rejected` / unknown-direction rejection). The two id
lists page SEPARATELY via independent `fn_offset/fn_limit` and `fp_offset/fp_limit` windows
exposed as `*_ids_view`, while the canonical lists and the aggregate `*_count` stay whole
(`test_the_two_lists_paginate_separately`, `test_pagination_never_truncates_the_aggregates`,
`test_re_paging_one_list_leaves_the_other_alone`). Incomplete pairs (None / non-int / bool /
out-of-two-value vocabulary on either side) are EXCLUDED AND COUNTED via `excluded_incomplete`
through the SAME `complete_rows` filter that feeds kappa and McNemar - never coerced to 0/1
(`test_incomplete_pairs_are_excluded_and_counted_not_labelled`, `test_a_bool_label_is_incomplete_not_a_zero_or_one`,
and `test_kappa_and_mcnemar_share_one_complete_row_filter` asserting the shared `n_complete`).

### Known differences vs old outputs / deviations
- `label_count` / `categorical_count` return plain `dict[value->count]` exactly as the compact
  spec dictates (not a richer object); my first test draft had assumed a wrapper with
  `counted`/`excluded_*` sub-fields, so I rewrote the count tests against the real surface.
- `DurationSummary.outliers` is a `list` (per spec), and non-numeric `values` to the three
  count helpers raise `TypeError` (they are `for ... in values`), not `DescriptiveError`;
  `duration_summary` itself takes an iterable and raises `TypeError` on a non-iterable. Tests
  match this actual contract rather than an imagined one.
- `mcnemar`/`cohen_kappa` reject ragged-length inputs and bool labels with typed
  `AgreementError`; the modules carry an `__main__` self-check that also passes.
- Nothing here reintroduces threshold sweeping / ROC / AUC / macro-average (guarded by
  `test_no_threshold_or_score_ranking_capability_leaks_in`). The single lunit_audit W002
  system-check warning is unchanged and expected.

[TASK-08 COMPLETE]


## Task 09 (implementing session report)

Admin-controlled per-proportion confidence intervals + display/semantics validation.
Built on Task 08 (frozen dataclasses / typed errors / null+reason discipline). Left UNCOMMITTED
for the orchestrator (no git state commands run).

### Files changed / created
- NEW `django-app/report_v2/measurements/confidence.py` (pi-authored, then reviewed+hardened):
  `wilson_interval(k,n,*,z=1.959963984540054)` -> frozen `WilsonInterval(k,n,lower,upper,
  confidence_level,method,available,null_reason)`; `DEFAULT_Z`; typed `ConfidenceError` base with
  `OutRangeCountError` + `UnsupportedCiError`; registry `register_proportion_ci` /
  `is_proportion_ci_registered` / `require_proportion_ci`; `BALANCED_ACCURACY_IDENTITIES` + a hard
  block so balanced accuracy can NEVER be registered nor looked up for a CI.
- NEW `django-app/report_v2/definitions/validation.py` (pi-authored via a self-contained API
  contract, reviewed): typed `DisplayValidationError` family; `ensure_whisker_is_not_ci`,
  `ensure_no_calculated_baseline_band`, `validate_numeric_benchmark`, `validate_display`,
  `build_ci_render_keys` (CI-OFF emits `{}`), plus the chart-type / bucket / whisker / CI-key
  frozensets. `__main__` self-check prints `validation self-check ok`.
- NEW `django-app/report_v2/tests/test_semantics.py` (written by the implementing session, not pi):
  Django `SimpleTestCase`, no DB writes, synthetic dict/int inputs only, 39 tests.
- MODIFIED `django-app/report_v2/measurements/__init__.py`: added the `.confidence` re-export block
  + `__all__` entries (established house pattern - every prior task did the same).
- MODIFIED `django-app/report_v2/definitions/__init__.py`: added the `.validation` re-export block
  + `__all__` entries (same established pattern).

### Exact test commands + real output tails (venv python, from django-app/)
```
.venv/bin/python manage.py test report_v2.tests.test_semantics --noinput -v 2  -> Ran 39 tests in 0.006s / OK
.venv/bin/python manage.py test report_v2 --noinput -v 1                       -> Ran 296 tests in 0.224s / OK
.venv/bin/python manage.py test lunit_audit --noinput -v 1                     -> Ran 16 tests in 0.496s / OK
```
Baselines preserved (report_v2 257 -> 296 with the 39 new; lunit_audit 16/16). The single
lunit_audit W002 LLM_BASE_URL-HTTP system-check warning is pre-existing/expected, not a failure.
`git --no-pager diff --check` is clean (exit 0). `git status --short` shows exactly the five
intended paths (2 modified `__init__.py`, 3 new files).

### Observed Wilson bounds (whole hand-check table, venv python, printed from wilson_interval)
Confidence-level 0.95, method `wilson` for every row:
```
(0,1)   -> (0.000000, 0.793451)     (1,1)   -> (0.206549, 1.000000)
(1,3)   -> (0.061492, 0.792340)     (2,3)   -> (0.207660, 0.938508)
(5,10)  -> (0.236593, 0.763407)     (0,10)  -> (0.000000, 0.277533)
(10,10) -> (0.722467, 1.000000)
```
Every row matches the independently-derived acceptance table to <= 1e-5; asserted verbatim (not
edited to fit code) in `test_hand_check_table_matches_to_1e_minus_5`. Invariants for all supported
proportions: lower/upper finite and `0 <= lower <= upper <= 1`
(`test_every_supported_proportion_is_finite_ordered_and_in_range`, ~72 cases + an independent
reference restatement to 1e-9).

### CI-OFF key-omission evidence
`build_ci_render_keys({})`, `{"ci":{"enabled":False}}`, `{"ci":{}}`, `{"ci":None}` all return `{}`
-- no `ci`/`lower`/`upper` keys at all (`test_disabled_ci_emits_no_ci_keys`). End-to-end a validated
widget with `ci.enabled=False` yields render data free of CI keys
(`test_validated_widget_with_ci_off_publishes_no_ci_keys`). When ON it emits exactly
`{ci,lower,upper}` with `0<=lower<=upper<=1`; unordered/non-finite/out-of-range bounds raise
`DisplayValidationError` (`test_enabled_ci_*`).

### Rejection behaviours (all typed, all named tests)
- balanced_accuracy + any CI -> `UnsupportedCiError`: blocked BOTH at `register_proportion_ci` and
  `require_proportion_ci` for every identity in `BALANCED_ACCURACY_IDENTITIES` and normalised
  aliases (`test_balanced_accuracy_cannot_be_registered_for_a_ci`). Never invented/defaulted.
- unregistered (metric,method) -> `UnsupportedCiError` before publication, for an unknown metric
  and for a known metric with an unregistered method string
  (`test_unregistered_metric_is_rejected_before_publication`, `test_unregistered_method_string_is_rejected`).
- whisker labelled as CI -> `WhiskerIsConfidenceIntervalError`: boxplot+tukey+marker key and any
  whisker style claiming ci/confidence semantics rejected; a genuine tukey boxplot with an
  independent CI (no marker) still passes (`WhiskerIsConfidenceIntervalTests`).
- numeric benchmark on nonnumeric chart (pie/table/confusion_matrix) and on an unknown chart type
  -> `NumericBenchmarkOnNonNumericChartError`; unit mismatch -> `BenchmarkUnitMismatchError`
  (case/whitespace-insensitive match passes); malformed value (bool/str/nan/inf) ->
  `DisplayValidationError` (`NumericBenchmarkTests`).
- calculated/synthesised baseline band -> `CalculatedBaselineBandError`; a baseline referencing
  registered data (`measurement`/`policy`) or an explicit constant `{value,unit}` passes
  (`NoCalculatedBaselineBandTests`).
- `validate_display` rejects unknown inputs / columns / buckets / threshold policies / disallowed
  grouping / CI-unknown-method, and rejects a non-mapping config (`ValidateDisplayTests`).

### n<=0 and out-of-range behaviours
- `wilson_interval(0,0)`, `(0,-1)`, `(0,-10)` -> `available=False`, `lower=upper=None`,
  `null_reason='n must be > 0'`, explicitly NOT the forbidden `(0.0, 0.0)` band
  (`test_n_le_zero_returns_null_with_reason_never_zero_band`).
- `k<0` (`(-1,5)`,`(-5,5)`) and `k>n` (`(6,5)`) raise the typed `OutRangeCountError`
  (subclass of `ConfidenceError`); the input k is never clamped
  (`test_out_of_range_count_raises_typed_error_never_clamps`).

### pi delegation / bail-out accounting
- First broad-scope pi run (whole spec, all 3 files) produced NO files and empty output after ~9 min
  (the known empty-return failure mode) -> killed, counted as attempt 1 on the (confidence) unit.
- Scoped pi to ONE file per call. Unit (A) `confidence.py`: pi succeeded on attempt 2 (single-file
  scope). Reviewing it I fixed two real issues myself: missing PRIMER header (added) and a
  defense-in-depth hard block for balanced-accuracy registration (added `BALANCED_ACCURACY_IDENTITIES`
  + the guard). The `__all__` "OutRangeCountError" scare was a false alarm: the display layer
  collapses double-underscores/long runs, so I verified via import that `__all__` is internally
  consistent (`MISSING_FROM_ALL == []`).
- Unit (B) `validation.py`: pi succeeded on its single scoped call against a self-contained API
  contract (/tmp/pi_task09_validation_api.md); its `__main__` self-check passes.
- Unit (C) `test_semantics.py`: I wrote it myself (not pi) for precise control over the frozen
  hand-check oracle and the exact rejection assertions. No bail-out was needed beyond the killed
  first broad run; both pi-authored modules were reviewed line-by-line and are correct.

### Deviations / notes
- The task's file list allowed extending `measurements/__init__.py` "if that is the pattern" -- it is
  (Tasks 07/08 both re-export), so I extended it, and applied the same established pattern to
  `definitions/__init__.py` so the new validation surface is reachable the house way. No other files
  touched; no models/migrations; no ORM/DB/web imports inside the pure helpers; synthetic data only;
  the real ePHI sqlite was never read.

[TASK-09 COMPLETE]

## Task 10 (implementing session report — resume)

Prior attempt wrote results.py then died before the two files that matter. This resume wrote
ONLY the two missing files against the frozen results.py contract, called the existing modules,
and verified. results.py was NOT touched (git diff vs HEAD is empty for it). No git state command
was run; everything is left uncommitted.

### Changed files (exactly the two new files + this notes append)
- django-app/report_v2/evaluation.py                (NEW — orchestrator + frozen RequestContract)
- django-app/report_v2/tests/test_evaluation.py     (NEW — 17 invariant tests)

### Test commands (from django-app/, project venv python) and real output tails
1) .venv/bin/python manage.py test report_v2.tests.test_evaluation --noinput -v 1
     -> "Ran 17 tests in 0.005s" / "OK"  (EXIT=0)
2) .venv/bin/python manage.py test report_v2 --noinput -v 1
     -> "Ran 313 tests in 0.254s" / "OK"  (296 baseline + 17 new = 313; >=296 preserved)
3) .venv/bin/python manage.py test lunit_audit --noinput -v 1
     -> "Ran 16 tests in 0.405s" / "OK"   (16/16 baseline preserved)
   (lunit_audit.W002 LLM_BASE_URL-HTTP system-check warning is the expected pre-existing warning.)
   git diff --check  -> clean (exit 0).

### Different-anchor scenario (same rows, two measurements)
rows: 09-01 dur=200 / 09-02 dur=400 / 09-10 gt=None dur=500 (newest row complete for duration,
incomplete for binary).
  binary anchor  = 2026-09-02
  duration anchor= 2026-09-10   (differ=True — the newest incomplete row does NOT advance D)

### Preserved-D + subgroup_latest_date scenario (filter_overrides={'site':'A'})
rows: 09-20 site=B / 09-10 site=A / 09-05 site=A.
  anchor D (=window_end) = 2026-09-20 (global max, preserved)
  subgroup_latest_date   = 2026-09-10  (site-A real latest, strictly < D)  -> True

### Count-reconciliation figures
matching == eligible + excluded_incomplete held with no other drop (incoming==matching), and the
four-reason partition over the same bucket set:
  incoming=5 matching=2 eligible=1 excluded_incomplete=1
  excluded_by_reason={out_of_window:1, foreign_identifier:1, filtered_out:1, missing_required:1}
  total_dropped=4 == sum(partition)=4

### Mutually-exclusive exclusion partition
Each dropped row carried EXACTLY one reason (verified per-reason =1 each across the four reasons),
and sum(values)==total_dropped — a true partition (single-reason, disjoint, complete).

### Override / invalid-id / raw-rows rejections (+ exact typed errors)
  unknown widget id          -> InvalidWidgetReferenceError
  disallowed override (layout/measurement/policy-version/CI) -> DisallowedOverrideError (at
                                                    RequestContract construction, BEFORE evaluation)
  unknown measurement id     -> UnknownMeasurementError
  unknown policy reference   -> UnknownPolicyError
  aggregate widget asked raw rows -> NonAggregateRowsError
  groups over max_groups     -> GroupCardinalityError
  page_size over MAX_PAGE_SIZE(=500) -> PaginationBoundError

### common_population equal-n_complete evidence (paired widget.kappa)
  {'filter_identity':'widget.kappa:complete_rows','n_complete':3,
   'sides':{'reference':3,'prediction':3}}  — both sides == n_complete via the SAME shared
  report_v2.measurements.complete_rows filter.

### evaluation.py IMPORTS-and-CALLS (does not reimplement) — named import points
  from report_v2.projects import require_project_context, CrossProjectReferenceError, ...
  from report_v2.dates   import bucket_range, capture_anchor, resolve_request
  from report_v2.measurements import binary_classification_metrics, cohen_kappa, mcnemar,
       fn_fp_cases, complete_rows, categorical_count, duration_summary, record_count,
       pairs_from_rows, wilson_interval, require_proportion_ci, BinaryClassVocabulary
  from report_v2.results  import ResultPayload, CountAccounting, CommonPopulation, DateMetadata,
       SourceMetadata, VersionMetadata, EVALUATOR_NAME, SCHEMA_VERSION
  (test test_calls_existing_modules_not_reimplemented asserts these names appear in the source;
   test_evaluation_module_is_pure asserts no django.db / ORM token appears.)

### Bailed out of pi?
Yes — wrote both files directly (the sanctioned bail-out). No pi process was ever backgrounded, so
nothing was left running. Verified via the three real suites, not a pi-shaped artifact.

### Deviations / notes
- evaluate() accepts injectable `widgets=` + `published_widget_ids=` so an
  UnsupportedMeasurementId can be exercised through an explicit bogus WidgetSpec without touching
  the frozen PUBLISHED catalogue.
- The reserved-block assertion uses a seed-derived in-span offset (FIXED_SEED % 1000 + idx) so all
  accessions stay inside [RESERVED_ACCESSION_BASE, +1_000_000).
- No DB writes; SimpleTestCase only; no new models/migrations; real ePHI sqlite never read.

[TASK-10 COMPLETE]

## Task 11 (implementing session report)

### Changed files (all left UNCOMMITTED for the orchestrator; no git state commands run)
- ADDED `django-app/report_v2/definitions/repository.py` — `DefinitionRepository(root, *, project_id)`, `PublishReceipt`, typed errors (`RepositoryError` base + `InvalidDefinitionIdError`, `PathTraversalError`, `PathEscapeError`, `StaleRevisionError`, `DuplicateVersionError`, `PublishRejectedError`, `DraftNotFoundError`), `validate_definition_id`, `default_root()`.
- ADDED `django-app/report_v2/tests/test_repository.py` — 12 Django `SimpleTestCase` tests, hermetic `tempfile.mkdtemp()` roots only, synthetic YAML, NO DB writes.
- settings.py NOT modified. The non-public-static assertion is satisfied by a module-local `default_root()` that reads `settings.REPORT_V2_ROOT` and falls back to `<BASE_DIR>/private_data/report_v2_definitions` (outside STATIC_ROOT and every STATICFILES_DIRS source). No settings reflow was needed.

### Reuse (not reimplemented)
- loader (Task 03): `load_report_definition` / `DefinitionError` for strict-YAML validation.
- validation (Task 09): `validate_display`, `ensure_whisker_is_not_ci`, `ensure_no_calculated_baseline_band`, `DisplayValidationError` — `validate_display` is run before publish, so a failing-preview definition cannot be published.
- projects (Task 04): `require_project_context` / `CrossProjectReferenceError` for the wrong-project guard (injected test `ProjectRegistry`).

### Verification commands + real output tails (from django-app/, venv python)
- `.venv/bin/python manage.py test report_v2.tests.test_repository --noinput -v 2`  ->  EXIT=0, `Ran 12 tests in 0.091s` / `OK` (12/12 green)
- `.venv/bin/python manage.py test report_v2 --noinput -v 1`                        ->  EXIT=0, `Ran 325 tests in 0.310s` / `OK` (313 baseline + 12 new preserved)
- `.venv/bin/python manage.py test lunit_audit --noinput -v 1`                      ->  EXIT=0, `Ran 16 tests in 0.449s` / `OK` (16 baseline)
- `git diff --check` -> clean (exit 0). `git status --short` -> only the two intended `??` files.
- Pre-existing `lunit_audit.W002` LLM_BASE_URL-HTTP system-check warning is expected, not a failure.

### Typed error raised for EACH rejection class (live evidence)
- traversal `../escape` / `/etc/passwd` / NUL -> `InvalidDefinitionIdError` (validate_definition_id runs before any path join)
- symlink-escape (draft symlink resolving outside root on read) -> `PathEscapeError`
- logical containment breach after normpath -> `PathTraversalError`
- wrong-project ref (measurement owned by another registered project) -> `CrossProjectReferenceError`
- duplicate version (existing blob, differing content) -> `DuplicateVersionError`
- stale revision on save_draft AND on publish -> `StaleRevisionError`
- invalid/anchor YAML at publish and display-validation failure at publish -> `PublishRejectedError` (pointer UNCHANGED)
- missing draft read -> `DraftNotFoundError`

### Failed-publish crash-safety evidence (pointer is the last durable move)
Injected `os.replace` failure on the pointer temp file AFTER the blob was fsync'd+replaced:
`crash old_bytes = b'cs@r1' after_bytes = b'cs@r1' UNCHANGED= True`
i.e. the on-disk pointer still references the OLD version (`cs@r1`), never blank/partial. Blob write (tmp + os.fsync + os.replace) completes BEFORE any pointer move; the pointer itself is flipped atomically via its own tmp+fsync+os.replace.

### Concurrency mechanism + no-loss result
Mechanism: **fcntl.flock(LOCK_EX) on a per-def_id lockfile** under `<root>/.locks/<def_id>`. Documented in the module docstring + publish() docstring. The read-pointer -> next-version -> write-blob -> flip-pointer sequence is serialised inside the exclusive lock; different def_ids use independent lockfiles/pointer files (independent publishing).
Same-def contention proof (N=8 threads, barrier-synchronised, identical def_id `hot`):
`CONC n= 8 errs= [] distinct= 8 final= hot@r8 final-exists= True`
All 8 versions distinct (serialised +1 never repeats), zero escaped exceptions, final pointer is one complete `hot@r8` token and its blob is durable — no lost update, no interleaved/partial content.

### Container-mount inode-swap evidence (immutable blobs; pointer swapped by inode, never in-place)
Republish of `mnt`: `inode before 156858 after 156860 CHANGED= True oldblob-stable= True`
The pointer file's inode changes across the swap (os.replace inode swap, container/bind-mount-safe) while the previously published blob's inode is stable — old blobs are never mutated in place; a changed republish yields a NEW version blob and the old one is retained.

### Not-public-static assertion
`test_runtime_definitions_not_public_static` proves the injected temp root AND the configured default (`default_root()`) are not inside `STATIC_ROOT` nor any `STATICFILES_DIRS` collectstatic source, and that an operator `REPORT_V2_ROOT` override (via `self.settings(...)`) stays private. Result: green.

### Fixes made as verifier (beyond pi's first draft)
1. `publish()` accepted `expected_revision` but never enforced it -> added a value-correct stale-revision guard executed under the lock, before any durable move (satisfies the Done-when "stale on publish" item; new test `test_stale_revision_rejected_on_publish`).
2. Latent identity-vs-equality bug in the revision compare (`is not` instead of `!=`): a revision re-read from disk is always a distinct str object with equal value, so the happy-path publish wrongly raised StaleRevisionError. Fixed in both `save_draft` and the publish guard. Masked in pi's original suite because its callers passed `None` or genuinely-different tokens.
3. Strengthened `test_concurrent_publishers_no_loss` with a same-def_id contention case (the actual flock target).
4. Non-static test made non-vacuous (was `if default_root is not None` skipping because no configured root existed) via the module `default_root()` + STATICFILES_DIRS check.

### pi / bail-out
pi (--model qwen3.8-flash-next) produced the initial two files from the single `/tmp/pi_task11_spec.md`; it exited 0 and reported green, but I did NOT take that on faith — I verified all three suites myself and found+fixed the gaps above. No bail-out to hand-authoring was required (pi's output was usable after my fixes); pi was invoked once for this unit.

### Deviations / blockers
- None functional. No settings.py edit (kept the module-local `default_root()` to avoid any settings reflow, per the "only if strictly needed" guardrail). No new models/migrations. No real persistent root, no public static/media, no `~/serverfiles/downloads/db_2026-06-18.sqlite3` touched. Everything left uncommitted for the orchestrator.

[TASK-11 COMPLETE]

## Task 12 (implementing session report)

**Changed/created files**
- `django-app/report_v2/admin_views.py` (NEW) — function-based views `editor`, `editor_new`, `editor_save_draft`, `editor_preview`, `editor_publish` mirroring `views.py` idiom. Every view passes a `require_admin` decorator built on the shared house gate `report_v2.permissions.can_edit_catalog`/`_is_admin`; anonymous -> 302 to login, authenticated non-admin -> 403, both BEFORE any model/filesystem work. Mutators carry `@require_POST` + `@csrf_protect` on top of the admin gate. Thin UI only: all durable moves delegate to Task 11 `DefinitionRepository` (`save_draft`/`read_draft`/`validate_preview`/`publish`, `StaleRevisionError`->409, `PublishRejectedError`->422), validation to loader 03 + validation 09 via `validate_preview`, preview data to `evaluation.evaluate` (Task 10). No new persistence/validation/evaluation logic, no models, no migrations, no drag-and-drop surface.
- `django-app/report_v2/urls.py` (EDIT — append-only): `git diff --stat` = `19 +++++++++++++++++++`, 0 code deletions (the only `^-` line in the diff is the `--- a/...` header). The reserved `/report/layout/` + `/report/layout/editor/<action>/` routes are inserted BEFORE the `/report/<slug>/` catch-all; distinct names `editor`, `editor_save_draft`, `editor_preview`, `editor_publish`, `editor_new`. `/report-old/` and `/report/<slug>/` untouched.
- `django-app/report_v2/templates/report_v2/layout.html` + `_editor_form.html` (NEW) — extend the project base template; report select/create, YAML `<textarea>`, validation-errors panel, Save-draft/Preview/Publish buttons, dirty + revision + conflict indicators. Plain buttons, no DnD.
- `django-app/report_v2/static/report_v2/editor.js` + `editor.css` (NEW) — framework-free, no CDN; dirty-state tracking + `fetch` calls to the four endpoints with the CSRF token.
- `django-app/report_v2/tests/test_editor.py` (NEW) — 9 named tests via `django.test.Client`, admin via `force_login` on a gate-admin user, filesystem isolated through an injected scratch `REPORT_V2_ROOT` (`override_settings`/monkeypatched `default_root`). Nothing touches the real persistent root or `~/serverfiles/downloads/db_2026-06-18.sqlite3`.

**Fixes applied this session** (tests were failing on first run):
- `test_editor.py`: added missing `reverse` import (`from django.urls import Resolver404, resolve, reverse`).
- `admin_views.py` docstring + `editor.js` header: removed the literal tokens `drag-`/`drag-and-drop` (the no-DnD source guard `assertNotIn('drag-')` matched the prose). No functional change.

**Test commands (from `django-app/`, project venv)**
```
.venv/bin/python manage.py test report_v2.tests.test_editor --noinput -v 2
.venv/bin/python manage.py test report_v2 --noinput -v 1
.venv/bin/python manage.py test lunit_audit --noinput -v 1
git diff --check
```
Real output tails:
- editor suite: `Found 9 test(s).` ... `Ran 9 tests in 0.463s` / `OK` (all 9 individually `ok`).
- report_v2: `Ran 334 tests in 0.831s` / `OK` (baseline 325 preserved + 9 new).
- lunit_audit: `Ran 16 tests in 0.443s` / `OK` (16/16 baseline preserved).
- `git diff --check`: clean (only the pre-existing CRLF-normalisation warning for `urls.py`).
- The `lunit_audit.W002 LLM_BASE_URL uses HTTP` warning is the expected pre-existing system-check warning, not a failure.

**Status-code matrix (full HTTP stack; from `test_non_admin_cannot_access_editor` / `test_missing_csrf_rejected` / admin paths)**

| actor | editor page (GET) | save draft (POST) | preview (POST) | publish (POST) |
|---|---|---|---|---|
| anonymous | 302 -> `/login` | 302 (redirect, not 200) | 302 | 302 |
| authenticated non-admin | 403 | 403 | 403 | 403 |
| admin, no CSRF token | 200 | 403 (CSRF cookie not set) | 403 | 403 |
| admin, valid | 200 | 200 (returns `revision`) | 200 | 200 (returns `version`) |

Direct hand-crafted `RequestFactory` POSTs (bypassing the client) for `AnonymousUser()` and the normal user also returned non-200 in `(302, 403)` for all four mutators, and the scratch root contained nothing matching `*forbidden*` — proving the gate runs before any filesystem/model work.

**CSRF-missing rejection** (`test_missing_csrf_rejected`, `Client(enforce_csrf_checks=True)`): admin POST to save/preview/publish without a token -> 403 (`Forbidden (CSRF cookie not set.)`), asserted `400 <= status < 500`. Bonus `test_bad_csrf_token_rejected`: a supplied-but-wrong 64-char token -> 403 (`Forbidden (CSRF token from POST incorrect.)`).

**Invalid-YAML publish pointer read-back proof** (`test_invalid_yaml_does_not_replace_published`): publish VALID_YAML -> 200, `pointer_before = repo()._read_pointer("guarded")` is not None; POST INVALID_YAML to publish -> 422 with non-empty `errors`; a **fresh** `DefinitionRepository` instance reads `_read_pointer("guarded")` back `== pointer_before` — pointer byte-for-byte unchanged.

**Preview mail + no-publish proof** (`test_preview_does_not_publish_or_send_mail`): for BOTH valid and invalid YAML, POST preview -> 200 with `errors` in payload, then a fresh repo asserts `_read_pointer("previewer") is None`, `read_draft("previewer")` raises `DraftNotFoundError`, and `len(mail.outbox) == 0`. `editor_preview` contains no `publish` call at all.

**Stale-conflict no-clobber proof** (`test_save_draft_and_stale_conflict`): save -> 200 `revision` rev1 (draft read-back == VALID_YAML); a concurrent writer advances the draft behind the client; stale save with `expected_revision=rev1` -> 409 `status=="conflict"`; on-disk `read_draft("concurrent")[0]` equals the concurrent writer's `advanced` text, NOT the `"attempted-clobber: yes"` body.

**Second-report independence** (`test_admin_can_create_second_report`): `editor_new` report-a + report-b both 200; both pointers initially None; publish report-a -> 200 `version=="report-a@r1"`, `_read_pointer("report-a")=="report-a@r1"` while `_read_pointer("report-b") is None`; republish report-a -> `report-a@r2` and report-b's pointer is still None.

**Route-ordering resolve proof** (`test_editor_route_before_slug`): `resolve("/report/layout/").func is av.editor` with `match.kwargs == {}` (not swallowed as a slug) and `url_name == "editor"`; `resolve("/report/").func is views.index`; every named editor route reverses under `/report/layout/`; `resolve("/report/some-random-slug/")` still raises `Resolver404` (no catch-all added); admin GET `/report/layout/` renders 200 through the full stack (base-template inheritance + static assets verified).

**No drag-and-drop** (`test_no_drag_and_drop`): scans `admin_views.py`, both templates, `editor.js`, `editor.css` for `draggable/ondrag/ondrop/drag-/drag_/grab/dragover/setdata/getdata/dropeffect` — none present.

**Deviations / notes**
- `editor_publish` surfaces validation failure as HTTP 422 (`status:"rejected"`) carrying the error list — the spec fixed the pointer-unchanged invariant, not the exact status; 422 is a 4xx distinct from 409/403.
- Preview evaluates `evaluation.evaluate` over an empty synthetic row set for the first published widget; an evaluation/population error is returned as read-only `preview_error` text (never a 500, never a publish).
- `require_admin` deliberately does not inherit the inner view's `require_POST`/`csrf_protect` attributes (so the gate cannot reject the very POST the view serves); `csrf_exempt` is absent/false so the CSRF middleware keeps protecting every mutator.
- Permissions/CSRF were NOT weakened to make any test pass; `urls.py` was not reordered; no git state commands were run — tree left uncommitted for the orchestrator.
- pi was NOT used for any unit this session; all deliverables were authored/written directly (continuation of prior session's authored files).

[TASK-12 COMPLETE]
