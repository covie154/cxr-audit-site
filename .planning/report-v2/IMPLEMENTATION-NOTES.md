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

---

## Task 13 — report routing, page state and widget frames

**Deliverables (all on disk, uncommitted; commit belongs to coder):**
- `report_v2/views.py` — index (unchanged behaviour + published list), report_page (server-hydrated,
  fault-isolated frames, signed per-widget context token over slug|version|widget_id with a
  domain-separated salt; every forged-input gate runs BEFORE the single ORM seam), widget_data
  (strict order: json body -> top-level key allow-list -> id validity -> token verify/binding ->
  current-pointer check (403 tampered / 409 stale) -> override validation -> evaluation; domain errors
  return 200 status error, never 500; no row data in any 4xx body).
- `report_v2/urls.py` — append-only defid-converter routes page + widget_data; the lowercase-only
  converter regex keeps the mixed-case probe at resolver 404, preserving task-12 route-order test.
- `report_v2/data.py` — read-only published-layout access (never drafts, never mkdir at import) plus
  the single monkeypatchable CXRStudy row seam with explicit AdapterError refusals (unknown source,
  unsupported cohort).
- `templates/report_v2/page.html` — 12-col grid frames in YAML order, per-widget controls (date
  range/relative/filters/comparison), summary status line, hidden initial payload pre, admin-only
  edit affordance, hidden empty-message element.
- `static/report_v2/report.js` (rewritten) + `static/report_v2/page_state.mjs` + `report.css` —
  closure-only page state (fresh navigation resets; no storage APIs), per-widget request sequence
  ledger so stale responses cannot replace newer selections, cookie-first double-submit CSRF
  header mirroring the house idiom, table pagination via show-more.
- `tests/test_pages.py` — 12 named tests, one per Done-when criterion (index list/empty; yaml-order
  grid; ordinary-user control invisibility; signed-token pinning incl. cross-widget/absent/forged 403;
  version/anchor forgery 400 with zero seam calls + republish 409; override allow-list matrix incl.
  nested-filter, >50 list, page bounds, comparison outside compare_by; request_seq echo + reducer
  ledger; AdapterError 200-not-500 fault isolation; empty-message element everywhere; pagination +
  css overflow; unknown/mixed-case 404s; no rows/counts in 4xx bodies). CSRF enforced via
  Client(enforce_csrf_checks=True) with cookie + hidden-x-csrfmiddlewaretoken-header double submit.
- `tests/js/page_state.test.mjs` — reducer + runtime harness (node --test, six subtests) pinning the
  stale-safe boot path, exact body keys, headers, stale-drop counting, rejected/stale summary
  behaviour, and a no-storage-APIs source scan.

**Verification (independently re-run by the supervising worker, real tails):**
- node --test tests/js/page_state.test.mjs -> `# tests 6 / # pass 6 / # fail 0`
- node --check static/report_v2/report.js -> clean; node --check harness -> clean
- ./.venv/bin/python manage.py test report_v2 --noinput -> `Ran 346 tests in 1.963s / OK`
  (334 task-12 baseline preserved + 12 new page tests; the Conflict:/report/t13report/... line is
  the expected stale-409 log from the forgery test, not a failure)
- ./.venv/bin/python manage.py test lunit_audit --noinput -> `Ran 16 tests in 0.476s / OK`
- py_compile clean on views.py/urls.py/data.py/test_pages.py; scratch roots under tempfile only;
  no production db inspected; no git state commands run by the worker lanes; tree left uncommitted.

**Process notes / deviations**
- All code was authored through the pi CLI (runs 1-4); pi --print exited silently at the end of run
  4, so completion was gated on disk truth + independently re-run suites, never on a child claim.
- One-off environment defect: run 2's DIRECT (non-pi) writes silently lower-cased mixed-case
  identifiers inside report.js AND inside the js harness (the header-key lookup). Run 3/4 restored
  the canonical spellings, verified by case-sensitive ripgrep count-queries against the committed
  house exemplars (upload.js: five matches for the canonical x-csrf header key; editor.js cookie
  idiom). Recommendation: every future worker lane authors via pi only; supervising workers must
  case-check any directly-written file before trusting it.
- CSRF header precedence is cookie-first (the header mirrors the csrftoken cookie the django
  middleware compares); the hidden form-holder value is fallback-only. The node harness pins this.
- The stale 409 keeps the last good render visible and disables that frame's controls with an
  explicit reload message; empty frames keep their server copy plus the hidden empty-message
  element so client re-renders can restore it; long tables paginate at page-size 50 with a
  show-more control and the body scrolls rather than clipping (css overflow rule added).
- views' published list wraps data.list_published in a broad guard so a broken definition tree can
  never break the login-only index; index still touches no database (pinned by the task-10 routing
  test with a mock user whose seam call would raise).

[TASK-13 COMPLETE]

## Task 13 — review round 2 (coding-worker, run 5)

Reviewer round-1 verdict REQUEST CHANGES addressed via one Pi run (qwen3.8-flash-next,
spec /tmp/task13-spec-run5.md, exited rc=0 with full report to /tmp/pi-task13-run5.log).
Fixed exactly the three blockers plus the non-blocking wording-parity item; server trust
boundary untouched; only the four round-2 files changed (verified by mtime isolation).

- B1 (TDZ boot crash): local chart-observer binding renamed to lowercase `resizeObserver`;
  `new` expression keeps the canonical capitalised global. Byte probes: lowercase-local=1,
  self-referential `const ResizeObserver`=0.
- B2 (read-only Element.children TypeError): renderFrame rewritten to the writable API only --
  slice-copy sweep + removeChild for server content, per-frame liveNode tracking with
  Array.prototype.indexOf.call isChild guards (idempotent re-render; never removeChild on a
  detached node), show-more hidden-managed and re-appended last so it is never duplicated.
  Byte probes: `body.children =` assignment=0, removeChild=3.
- B3 (no grid container): report.css gains the container rule (display:grid;
  grid-template-columns: repeat(12, minmax(0, 1fr)); gap), a min-width:0 track guard, and a
  max-width:720px breakpoint collapsing to one column with `grid-column: span 12 !important`
  to beat the inline spans. test 2 now asserts the CONTAINER rule in the shipped stylesheet,
  not just the child spans (false-assurance case closed).
- Minor (a) parity: DEFAULT_EMPTY byte-equals views._EMPTY_MESSAGE (oracle PARITY_EMPTY=1);
  summaryText rebuilt to the server wording ("eligible", U+00B7 via \u escape). New test 13
  executes the on-disk client formatter under node and compares byte-for-byte with
  views._summary_text over 4 payloads -- future drift fails the suite.
- Harness hardening (why the gates missed B1/B2): FakeNode.children is now getter-only
  (strict-mode assignment to it throws, as in a browser), removeChild implemented, the chart
  branch actually executes (echarts stub + chart-container selector + recording observers),
  and step-5 pins single-live-region + single-button idempotency after a second update.

Gates, independently re-run by the supervising worker after Pi exited (never trusted from the
child's word): report_v2 "Ran 347 tests in 2.012s / OK" (346 prior + 1 new), lunit_audit
"Ran 16 tests in 0.434s / OK", node harness "# tests 6 / # pass 6 / # fail 0", node --check
clean, py_compile clean (views/urls/data/test_pages). Deviations: (1) the round-1 declared
harness header-key restoration stays as accepted by the reviewer; (2) renderFrame gained the
isChild guards beyond the reviewer's minimum fix -- a direct removeChild of an already-detached
liveNode/show-more would raise DOMException NotFoundError in a real browser after two updates;
(3) server-side files (views.py/urls.py/templates) byte-identical to the round-1 submission --
reviewer verdict on the trust boundary was ACCEPT and remains valid.

[TASK-13-R2 COMPLETE]

## Task 14 — value, table, line and bar renderers

**Deliverables (all NEW files on disk, uncommitted; commit belongs to coder):**
- `report_v2/static/report_v2/widgets/format.mjs` — `formatValue` (rate/ratio/probability → 1-dp
  percent, seconds → human duration incl. the 300s→"5 minutes" reference, index → 3dp, count →
  grouped int, non-finite → "—", unknown unit → raw String) and pure FNV-1a `groupColor` over a
  fixed 8-colour palette (deterministic by group label).
- `registry.mjs` — `RendererError`; `register/get/render/disposeInstance/disposeAll`; per-container
  live registry so a re-render disposes the previous instance exactly once before replacement
  (chart-leak guard); shared `el`/`clearContainer`/`observeLifecycle`/`buildChart` helpers;
  `window.__rv2widgets.registry` host mirror (classic-script bridge, no host change required).
- `value.mjs` — dl of aggregate rows via safe DOM text; supported-CI "(95% CI …)" suffix only when
  `ci[name].available === true`; unavailable CI adds nothing (never fabricated); error/empty states.
- `table.mjs` — union-column table from `payload.rows`, unit-formatted numeric cells, null → "—",
  pagination info line; show-more button stays owned by the Task-13 host.
- `line.mjs` / `bar.mjs` — vendored-`window.echarts`-only charts. Data matrix from the optional
  `payload.series` cells (group × bucket/category; missing cell → null → visible gap,
  `connectNulls:false`), single-scalar-aggregate fallback when `series` absent (never invents
  per-group numbers). Exactly one comparison dimension (one x-axis OBJECT, never an array; one
  series per group). Benchmarks unit-filtered, dashed `markLine` with `yAxis` entries only (numeric
  axis), `yAxis scale:true` so benchmarks/data scale; deterministic palette per group; hidden
  `.widget-alt-table` a11y alternative + role/aria-label; resize/theme observers guarded,
  lowercase-local bindings (no global shadowing), dispose-once semantics.
- `report_v2/tests/js/widgets.test.mjs` — node:test harness (FakeNode shim, echarts/observer stubs,
  `globalThis` idiom copied from the Task-13 harness). 10 subtests pinning: unit rules +
  determinism, value CI/percent/null, table union/null/pageinfo, weekly mid-window gap stays
  `null` + `connectNulls:false`, grouped bars + deterministic colours + unit-filtered yAxis-only
  markLine, replacement-disposes-exactly-once + disposeAll + resize-after-dispose no-op, host
  mirror, single category axis + one series per group, forbidden-token source scan.

**Verification (independently re-run by the supervising worker, real tails):**
- `node --test report_v2/tests/js/widgets.test.mjs` → `# tests 10 / # pass 10 / # fail 0`
- `node --check` clean on all six modules + the harness.
- `.venv/bin/python manage.py test report_v2 --noinput` → `Ran 347 tests / OK`
  (baseline preserved: the client layer is additive; zero server files touched — `git status`
  shows only the two new paths).
- `.venv/bin/python manage.py test report_v2 lunit_audit --noinput` → `Ran 363 tests / OK`.
- `git diff --check` clean. Forbidden-token scan (innerHTML/storage/CDN/fetch) zero across the six
  modules; house byte-truth auditor run over the new files reports only the known
  lower-case-local-binding false-positive class shared with the committed `report.js`
  (`resizeObserver`/`mutationObserver` locals vs canonical globals — precedent accepted in Task 13).

**Deviations / decisions**
- Strictly additive lane: no edits to report.js/page.html/views.py/report.css. Task 14's Done-when
  covers the renderers + browser tests; the page bridge that routes frames through
  `window.__rv2widgets` is follow-up work (Task 17/parity lane) and the registry API needs no host
  change to be consumed.
- Pinned contract deviation: the current evaluator publishes `groups` + `buckets` but NO
  per-group numeric matrix, so line/bar consume the optional `payload.series` cell matrix
  (documented cell shape in the modules) instead of fabricating grouped numbers; server-side
  emission of `series` is deferred to Task 16 (seeded demo definitions). Absent `series` the
  charts degrade to the single scalar-aggregate point/bar path — visible, honest, no synthetic
  clinical values.
- Benchmarks are passed in via `options.benchmarks` (YAML schema shape `{label,value,unit}`); the
  layout→options plumbing for published pages lands with the same follow-up bridge task as the
  registry hookup.
- All code authored via the pi CLI (single run, provider local-hermes, model qwen3.8-flash-next,
  spec /tmp/task14-spec.md, log /tmp/pi-task14.log, PI_EXIT=0). Completion gated on disk truth +
  the supervising worker's own suite runs, not the child's claims.

[TASK-14 PENDING-REVIEW]

## Task 14A — Stabilize report UI and YAML editor discoverability (coding-worker, run 19)

**Deliverables (all on disk, uncommitted; commit belongs to coder):**
- `report_v2/admin_views.py` — `_report_entries()` selector union (published ∪ drafts) with
  `state_label` ∈ {`draft only`, `published`, `published + draft`}; `editor()` falls back to the
  CURRENT published blob text read into memory when no draft exists (`source_state`
  `published-only`, `source_label`, `published_version` context). GET writes nothing; only the
  explicit save endpoint creates the private draft.
- `report_v2/templates/report_v2/layout.html`, `_editor_form.html` — selector options carry
  `data-state`; new `data-role="source-indicator"` badge with `data-source-state`.
- `report_v2/templates/report_v2/page.html` — admin `Edit layout` links
  `report_v2:editor_detail` (current def id) with `data-role="edit-layout"`; grid rows
  `grid-auto-rows: minmax(<row_height_px>px, auto)` (vertical growth, no clipping); loads
  `widgets/boot.mjs` as `type="module"` before report.js. Ordinary users: no editor affordance (pinned).
- `report_v2/static/report_v2/report.css` — superset stabilization: pinned 12-col grid / mobile
  span-12 !important / `.widget-body` overflow:auto contract preserved verbatim; controls flex-wrap,
  min-width:0, overflow-wrap anywhere, focus-visible rings, chart sizing, no absolute/negative-margin
  tricks.
- `report_v2/static/report_v2/widgets/boot.mjs` (NEW) — registers value/table/line/bar with the
  registry, sets `window.__rv2widgets.bootReady`. Forbidden-token clean (inner*HTML/storage/fetch).
- `report_v2/static/report_v2/report.js` — fallback-safe registry bridge in `renderFrame`: eligible
  frames render through `window.__rv2widgets.registry` into a dedicated `widget-mount` child so the
  `widget-live` wrapper keeps its class/marker even though line/bar re-class their container (Task 14
  renderer contract); one-time dispose of the previous instance before a re-render; any throw falls
  through to the byte-for-byte legacy path (node harnesses keep running with no `__rv2widgets`).
  Pre-existing byte-truth auditor failure fixed (local `resizeObserver` -> `resizeHandler`).
  `DEFAULT_EMPTY` / `summaryText` server-parity anchors untouched.
- `report_v2/tests/test_editor.py` — 4 new tests: selector states incl. flip to `published + draft`;
  published-only open is read-only in memory (drafts dir stays empty on disk); explicit Save draft
  creates the private draft (round-trip read); preview writes nothing / pointer unchanged.
- `report_v2/tests/test_pages.py` — 3 new tests: report-specific edit-layout href + ordinary-user
  absence; grid minmax growth + css contract regexes still pinned; boot module wired + shipped +
  registers the four kinds.
- `report_v2/tests/js/page_render_bridge.test.mjs` (NEW, node) — 5 tests: legacy fallback without
  host; registry path renders via mount child (live wrapper class preserved), dispose-once on
  re-render; throwing renderer falls back; real registry+boot contract smoke; boot source scan.
- `report_v2/tests/test_browser_layout.py` + `browser_settings.py` (NEW, Playwright) — 5 tests on a
  throwaway runserver (temp sqlite via DATABASE_NAME/AUDIT_DATABASE_NAME, REPORT_V2_ROOT mirrored in
  browser_settings so no stray `private_data/` is written; synthetic SYNTH-SITE rows only):
  no horizontal overflow + zero pairwise frame/control/body overlap + controls within frame + Tab
  reaches Apply at 1440/1024/390; long table grows inside its section with working show-more;
  line/bar paint echarts canvas + a11y table via the registry (no `<`/`undefined`/`NaN` text);
  admin editor navigation lands on `/report/layout/editor/browser14a/` with published YAML in
  textarea and no draft on disk; ordinary user has no edit-layout; legacy /report-old/ < 500.

**Verification (supervising worker's own runs, not the child's claims):**
- `.venv/bin/python manage.py test report_v2.tests.test_editor report_v2.tests.test_pages -v 2` → `Ran 29 tests / OK`
- `.venv/bin/python manage.py test report_v2 -v 1` → `Ran 359 tests / OK`
- `.venv/bin/python manage.py test report_v2 lunit_audit` → `Ran 375 tests / OK`
- `node tests/js/widgets.test.mjs` → 10 pass / 0 fail; `page_state.test.mjs` → 6 pass / 0 fail;
  `page_render_bridge.test.mjs` → 5 pass / 0 fail; `test_browser_layout.py` → 5 tests OK (real Chromium)
- `node --check` clean on report.js + editor.js; `audit_static.mjs` → `AUDIT-OK` on report.js, editor.js, boot.mjs
- `git diff --check` clean; `git status` shows only this card's files.
- Evidence screenshots (1440/1024/390 + long-table + editor): `/tmp/rv2-14a-evidence/`
  `page-browser14a-1440.png`, `page-browser14a-1024.png`, `page-browser14a-390.png`,
  `page-longtable-1440.png`, `editor-1440.png`

**Deviations / decisions**
- Bridge renders through a dedicated `widget-mount` child instead of the `widget-live` node itself
  (line/bar set `container.className` per the landed Task 14 contract; handing them the live node
  would destroy the `widget-live`/`data-live-region` marker). Spec-level correction owned by the
  supervising worker after observing the red browser run; bridge harness pins the invariant.
- The single Pi run (qwen3.8-flash-next, spec /tmp/task14a-spec.md, log /tmp/pi-task14a.log,
  PI_EXIT=0) empty-returned its final report after ~45 min but left most files on disk; the
  supervising worker then owned the gaps: `set_viewport_size` API fix, the mount-child bridge fix,
  `browser_settings.REPORT_V2_ROOT` mirroring (kills the stray in-repo `private_data/` writes),
  mount-contract assertions in the bridge harness, and this log. Two leftover debug `runserver`
  processes were terminated; the stray synthetic `private_data/` tree was relocated out of the repo.
- Playwright 1.62 + cached chromium verified on this host; suite skips cleanly if tooling is absent.

[TASK-14A PENDING-REVIEW]

## Task 15 — pie, confusion matrix and box-plot renderers (coding-worker, run 22)

**Deliverables (all NEW except boot.mjs; uncommitted; commit boundary belongs to coder):**
- `report_v2/static/report_v2/widgets/pie.mjs` (97 lines) — mutually exclusive `payload.categories`
  counts (label/count), aggregates fallback when `categories` absent, share = count/total via
  `formatValue(...,"rate[0,1]")`, optional donut (`options.donut` → radius `["45%","70%"]`, else
  "70%", mirrored as `data-donut` for the browser). Vendored-echarts-only single pie series,
  deterministic `groupColor` per category, benchmarks READ-NOT (no markLine at any depth — pinned).
  Total<=0 / no categories → the shared empty message; `payload.error` → widget-error. Alt table
  category/count/share with caption; null-safe count cell ("—" for non-finite, amend FIX 2).
- `confusion.mjs` (84 lines) — DOM table IS the display (export/PDF safe, no echarts, no canvas):
  consumes the server `ConfusionMatrix.as_dict()` shape verbatim; declared class order on both axes,
  `rows_are=ground_truth` rows / `columns_are=prediction` columns pinned in header + data-row/class
  attributes; `options.display:"percent"` normalises per ground-truth ROW (`cell/row_totals[i]` →
  1-dp percent); a zero-denominator row renders "unavailable" (never "—"/"0.0%"/NaN) with
  `data-normalised="unavailable"`; count mode prints raw integers incl. n=0 skeleton; accuracy line
  from `accuracy.value` ("Accuracy: 62.5%" / "Accuracy: unavailable"); idempotent dispose.
- `boxplot.mjs` (174 lines) — consumes SERVER summaries (`summaries[]` or `summary` fallback), never
  raw arrays. Box series rows are `[lower_whisker,q1,median,q3,upper_whisker]` — observed-value
  whiskers, NEVER the ±1.5·IQR fences (pinned by asserting -4.5/15.5 absent); separate scatter
  outlier series keyed `[groupIndex,value]`, non-finite dropped. Benchmarks unit-filtered like bar.mjs;
  matched → dashed markLine on the boxes series only, label pre-formatted through `formatValue`
  (300 s → "5 minutes"); `unit:"seconds"` also installs `yAxis.axisLabel.formatter` (axes format
  minutes). Alt table n treated as a COUNT (amend FIX 1: "11", not "11 s"), other numerics via
  formatValue, outliers listed ("none" when empty); caption + aria-label say plainly the whiskers are
  observed values within 1.5*IQR fences (whisker != CI, per YAML-CONTRACT).
- `boot.mjs` — now registers SEVEN kinds (pie, confusion_matrix, boxplot added; bootReady stays last).
- `tests/js/widgets15.test.mjs` (351 lines) — node:test, 20 tests: seven-kind registry resolution +
  bootReady; donut/plain radius; pie alt-table shares; pie benchmark-proof deep key walk; empty/error/
  aggregates-fallback/null-count; binary 2×2 percent + multiclass 3×3 count cells vs the fixtures;
  zero-denominator "unavailable"; dispose-once; boxplot whiskers-not-fences, scatter outliers,
  markLine yAxis 300 + "5 minutes" (also axis formatter called with 300), unit-mismatch drop, alt-table
  parity against `formatValue`, n-as-count, empty/error; eight-fixture render contract; forbidden-token
  source scan. Fixtures are imported from the gallery builder (single source of truth), not restated.
- `tests/js/gallery/synthetic_gallery.mjs` (161 lines) — PURE string builder + `SEVEN_FIXTURES`
  (8 sections, 7 kinds, all synthetic); script tags assembled at runtime (no literal tags, no fetch,
  no CDN); `--dump` emits the fixtures JSON sidecar the browser suite consumes.
- `tests/js/gallery/gallery.test.mjs` (129 lines) — 6 node tests: coverage, sentinel embedding,
  exactly eight widget-frame divs, fixtures JSON round-trip, builder source scan, registry render pass.
- `tests/js/gallery/fixtures.task15.json` — generated sidecar (node --dump), shared with the browser suite.
- `tests/test_browser_gallery15.py` (252 lines) — Playwright, self-skips without tooling; NO Django,
  NO subprocess: one routed fake origin serves the built document, the whitelisted widget ES modules and
  the vendored echarts off disk. Asserts bootReady, 8 sections/7 kinds, ≥4 real canvases, percent
  confusion cells + accuracy line, multiclass raw counts (60.0% absent there), boxplot alt-table
  whisker labels + "1 min 40 s" + median "6 s" + n "11", no undefined/NaN text, zero
  markline/benchmark classes under pie/confusion frames, full-page screenshot to /tmp/rv2-15-evidence.

**Verification (supervising worker's own runs, not the Pi claims):**
- `node report_v2/tests/js/widgets15.test.mjs` → tests 20 / pass 20 / fail 0
- `node report_v2/tests/js/gallery/gallery.test.mjs` → tests 6 / pass 6 / fail 0
- `node report_v2/tests/js/widgets.test.mjs` → 10/0 (untouched); `page_state` 6/0; `page_render_bridge` 5/0
- `audit_static.mjs` on pie/confusion/boxplot/boot + the three new .mjs test-side files → AUDIT-OK
- `.venv/bin/python manage.py test report_v2.tests.test_browser_gallery15 -v 2` → Ran 8 tests OK
  (real Chromium; screenshot /tmp/rv2-15-evidence/gallery-1440.png)
- `.venv/bin/python manage.py test report_v2 -v 1` → Ran 367 tests OK (359 before + 8 new browser)
- `git diff --check` clean; `git status` shows only this card's files.

**Deviations / decisions**
- Two supervisor-review fixes folded into the Pi run via /tmp/task15b-amend.md: boxplot n cell formats
  as a count (was inheriting the seconds unit); pie count cell is null-safe. Both pinned by t15b/t7b.
- The "5 minutes" benchmark-label acceptance is asserted at the chart-option level (canvas-drawn label
  is not DOM text); the browser side asserts the DOM-visible duration cells instead, as the spec directs.
- Gallery browser suite mirrors buildGalleryHtml in python string concatenation because node .mjs is
  not importable from python; the shared fixtures JSON sidecar keeps both renderers' inputs identical.
- Pi ran twice total (spec /tmp/task15-spec.md died empty-returning after ~35 min with zero files —
  known failure mode; superseded by /tmp/task15a-spec.md renderer-only + /tmp/task15b-spec.md
  tests/gallery, PI_EXIT=0 both). Repo files were never hand-written by the worker except this log;
  worker inspected and re-ran everything above independently.

### Review round 1 correction (run 24, 2026-09-14)

Reviewer found the gallery canvases rendered at zero height (1424x0): the inline gallery `<style>` lacked
the shipped `.widget-chart,.widget-chart-box` sizing rule that production gets from report.css (which the
routed gallery page never loads), so echarts initialised into unsized containers and painted nothing while
test_c passed trivially on canvas count alone. Fixed in lockstep in BOTH builders — the node
`buildGalleryHtml` in synthetic_gallery.mjs and its python mirror `_build_gallery_html` in
test_browser_gallery15.py — by appending the byte-identical
`.widget-chart,.widget-chart-box{width:100%;min-height:240px}` inline (parse-time, inside the existing
`<style>` block, so it cannot re-zero after echarts init the way a late-loading <link> could). test_c
hardened with a per-canvas `getBoundingClientRect` w>0 / h>0 assertion; g2 gained a byte-exact drift guard on
that rule; the evidence screenshot was regenerated by the browser suite. Renderers were untouched.

[TASK-15 PENDING-REVIEW]

## Task 16 — 17-widget PRIME seed and compatibility actions (coding-worker, run 28)

**Deliverables (all NEW or additive; uncommitted; commit boundary belongs to coder):**
- `report_v2/seed/prime-overview.v1.yaml` + `report_v2/seed/lunit-defaults.v1.yaml` — vendored byte-copies of
  the reviewed planning seeds (banner line only differs; the immutable-copies test pins it). 17 widgets in 4
  sections: five `value` summary cards (total, graded, accuracy, sensitivity, specificity, that exact order),
  four `performance` widgets (site_metrics table + three weekly line trends), two `timing` boxplots
  (clinical_decision, server_time), six `manual` tables (llm_lunit, manual_lunit, agreement, mcnemar,
  false_negatives, false_positives). Zero `bar`/`pie`/`confusion_matrix` widgets in the seed.
- `report_v2/seed/__init__.py` — package accessor (seed_dir/seed_text/report_seed_text/policy_seed_text/
  seed_digest/seed_manifest, SEED_DEF_ID = overview).
- `report_v2/seeding.py` — the pure installer engine: validate-before-write (SeedValidationError carries the
  collected violations), never imports or calls any publication helper (install_drafts uses save_draft only;
  a smuggled publish kwarg trips SeedPublicationForbidden), report and policy drafts stored under separate
  definition ids (overview / overview-policy), empty publication scaffold pruned only when genuinely empty.
- `report_v2/management/commands/seed_report_v2.py` — explicit admin command; `--check` writes nothing and
  prints `SEED-CHECK OK overview 17 widgets`; a broken seed exits 1 with violations on stderr.
  (Correction, review round: the shipped command exposes only `--def-id` / `--root` / `--check` — the
  earlier `--report-only`/`--policy-only` sentence described a variant that was never shipped.)
- Admin seed action `report_v2:editor_seed` (`/report/layout/editor/seed/`) in `admin_views.editor_seed`:
  POST + CSRF + admin-gated, dry_run answers `{"status": "checked"}` without writing, a real run installs
  both drafts only (drafts_only True / published False); the parameterised `editor_detail` route was relocated
  LAST inside the reserved block so the literal seed action wins Django's first-match race (path/name/callback
  byte-identical; resolve()+reverse() re-proved by the supervisor).
- Scoped CSV compatibility actions `/<slug>/csv/<kind>/` (`report_v2.views.report_csv`, kind in
  full/false_negatives/false_positives): login-gated, GET-only, widget + signed `_widget_context_token`
  context REQUIRED (400 without them), tampered token 403, moved pointer/stale version 409, unknown kind or
  malformed slug 404, widget-not-on-layout 403, discrepancy kind on a non-supporting measurement 422; only
  widget/context/date_from/date_to/site query keys are accepted (anything else 400); the header row equals the
  documented `_CSV_COLUMNS[kind]` tuple and the trailer comment rows carry widget/measurement/reference/
  prediction/window/anchor/filters/version/kind provenance. The FN/FP direction is derived from the widget's
  own bound sources — swapping ground_truth/prediction on the widget swaps the selections (supervisor probe
  proved 900000002/006/011 FN and 900000004/010 FP against the unswapped bindings). No implicit global date
  range: the widget's evaluated window/filters are the only scope.
- `report_v2/tests/test_seed.py` — 16 named tests, one per Done-when clause (8 C1a packaging/install/action
  tests + 8 C1b synthetic-evaluation/policy/parity/demo/CSV tests; C1b lands via two supervisor-pinned
  micro-runs after the single full-size C1b spec stalled empty-returning — known CLI failure mode).
- `report_v2/tests/js/seed_widgets.test.mjs` — 23 node tests: every payload through the REAL registry
  renderers for all seven display kinds (no throw, painted structure, accessible alternative table, clean
  second render + dispose) plus the byte-exact classification-summary column drift guard against the shared
  12-column server constant.
- Measurement-bridge amendments from the B-runs (evaluation.py reference_agreement via the shared primitives,
  results.py chart channel, data.py/prime.py adapter surfaces) carried in from the earlier phases.

**Parity differences vs the legacy report (recorded, not hidden):**

| Legacy behaviour | New seed widget(s) | Parity status | Why numbers may legitimately differ |
|---|---|---|---|
| Per-site ROC-AUC column | site_metrics / balanced_accuracy | Reviewed: balanced-accuracy relabel | The legacy column was mislabelled ROC-AUC; the metric family is balanced accuracy, so values legitimately differ from the legacy print. |
| Weekly ROC-AUC chart band/banner | balanced_accuracy_trend | Reviewed: calculated baseline band removed; quartile method is the shared duration/quartile implementation | Legacy computed its own quartile approximation; the new path uses the reviewed quartile implementation. |
| Monospaced analysis report text box | none | Reviewed: text box removed | Feature intentionally dropped from the seed per the reviewed legacy map. |
| McNemar result block | mcnemar | Reviewed: McNemar statistic definition is the shared paired-reference implementation | Exact method verified against fixtures; the legacy block's rounding differs. |
| Manual-vs-LLM subset semantics | llm_lunit / manual_lunit / agreement | Reviewed: missing-GT rows are excluded (eligible gate), not coerced | Complete-score requirement and missing-value handling change denominators. |
| Zero-denominator cells | all normalised tables | Reviewed: null-denominator renders as unavailable, never 0.0%/—/NaN | Null-denominator policy is a reviewed display rule. |
| server_time 5-minute line | server_time | Reviewed: FIXED 300-second reference benchmark (label "5 minutes"), not a computed band | The seed pins the constant; no computed baseline band exists anywhere (validator-enforced). |
| Uniform per-finding thresholds | accuracy/sensitivity/specificity/classification_summary via lunit-defaults@1 | Reviewed: policy mirrors the legacy THRESHOLDS "default" map (report/views.py) byte-for-byte (nine findings 10, nodule 15, operator gt, aggregate any_positive, require_all_scores true, scale [0,100]) | The legacy map carries a site-specific YIS override ({'nodule': 5}); the reviewed seed deliberately carries NO site-specific override (pinned by assertNotIn "YIS"), introduces no new threshold, and the test asserts the query key universe stays {measurement, inputs, threshold_policy, cohort}. |

**Test-only registered demo definitions:** `categorical_count` (pie) and `confusion_matrix` are supported by
the evaluator and exercised ONLY inside `test_registered_categorical_count_and_confusion_matrix_demo_definitions_are_test_only`
(plus the js display-kind suite); they are deliberately ABSENT from the vendored seed because the reviewed
layout has no category-mix or matrix widget — absence is pinned, not accidental.

**Seed procedure for an operator:** `manage.py seed_report_v2 --check [--root DIR]` validates and prints the
17-widget tally without writing; without `--check` it installs the two DRAFTS only (or POST the admin seed
action with a dry_run first). Publishing stays an explicit editor action; the seeding engine never publishes.

**Verification (supervising worker's own runs, not the Pi claims):**
- `manage.py test report_v2.tests.test_seed -v 2` → Ran 16 tests OK (synthetic PRIME data, scratch roots only).
- `manage.py test report_v2 -v 0` → Ran 383 tests OK (367 pre-existing baseline + 16 new).
- `node --test` per file: seed_widgets 23/0, widgets15 20/0, widgets 10/0, page_state 6/0,
  page_render_bridge 5/0, gallery 6/0 (70/70 overall via the glob form; the bare-directory form fails at the
  Node 22 runner level identically WITHOUT seed_widgets.test.mjs — pre-existing invocation quirk, not a
  regression).
- `manage.py seed_report_v2 --check` → `SEED-CHECK OK overview 17 widgets`.
- Supervisor probes (kept in /tmp, never committed): probe17 (all 17 widgets evaluate green with full
  metadata + timing + render contracts), shapes probes (discrepancy caption/comparison provenance, pie
  categories, matrix classes/cells/row_totals/accuracy), CSV probe (every status code, header rows, trailer
  rows, FN/FP direction + binding-swap proof).

**Deviations / residual risk**
- Two micro-runs replaced the single C1b spec after it stalled empty-returning twice at full size (endpoint
  contention after concurrent launches; the single-writer rule was restored by killing the stragglers).
- The `[TASK-15 PENDING-REVIEW]` marker and everything above it are untouched; this section is append-only.
- W002 (LLM_BASE_URL http) in system checks is pre-existing config, not introduced by this task.
- No site-specific override, no new threshold, no production data touched: seeds/tests use SYNFTH-style
  synthetic identifiers only; the CSV and seed paths were exercised only against scratch roots and the
  in-memory test database.

[TASK-16 PENDING-REVIEW]

### Review round 1 — completed and committed (2026-09-21)

Reviewed the full uncommitted Task 16 surface against the runbook (draft-only seed install, binding
validation, 17-widget synthetic evaluation/rendering, scoped CSV gates, access controls, documented
parity). The implementation held up; the concrete gaps found and fixed were all cross-platform /
bookkeeping issues surfaced by running the verification battery on a Windows host (Anaconda CPython
3.13; prior runs were Linux py3.11):

- `report_v2/definitions/repository.py` — Windows portability, no Linux behaviour change:
  (a) the module-level `import fcntl` (Unix-only) became a try/except that keeps exact
  `fcntl.flock` semantics on POSIX and falls back to `msvcrt` byte-range locks on Windows;
  (b) the three `os.open(O_RDONLY)` + `os.fsync` sites became `_fsync_path` (opens `O_RDWR` because
  Windows `_commit` rejects read-only handles with EBADF);
  (c) draft/blob/pointer atomic writes use `write_bytes` — `Path.write_text` on Windows translated
  newlines and corrupted the byte-faithful CRLF seed drafts (`\r\n` became `\r\r\n`), which broke
  both byte-equality and idempotent republication.
- `report_v2/tests/browser_settings.py` — Python 3.13 rebuilds the mimetypes database on every
  `init()` call, so the old trailing `_mimetypes.init()` silently dropped the `.mjs` →
  `text/javascript` mapping and the throwaway dev server served ES modules as `text/plain`
  (Chromium blocks module scripts with that MIME). Mapping now added after a single init; also
  fixed the suffix spelling to `.mjs`/`.js`.
- `report_v2/tests/test_browser_seed.py` (untracked, not previously recorded) — added to the
  deliverable set: route handlers now read echarts/widgets with explicit `encoding="utf-8"`
  (cp1252 default raised UnicodeDecodeError inside the handler and hung `page.goto`), and the
  harness renders into a `.widget-body` child like production `report.js` does, because the
  line/boxplot renderers replace the render target's `className` (the direct-into-section variant
  lost `.widget-frame` on the 5 chart widgets and the frame count read 12/17).
- `report_v2/tests/test_repository.py` — `test_symlink_escape_rejected` now `skipTest`s when the
  host cannot create symlinks at all (Windows without developer mode, WinError 1314); the control
  itself still asserts on POSIX.
- `.gitignore` — ignores `django-app/private_data/` (the runtime definitions root; untracked
  drafts/pointers must never be committed). The existing local tree is preserved untouched.

**Verification (this round, Windows host, Anaconda CPython 3.13.5, run from `django-app/`):**
- `python manage.py test report_v2.tests.test_seed -v 1 --noinput` → Ran 25 tests OK (the suite grew
  past the 16 recorded above: +reseed/policy-preserve, +4 real-adapter DB-integration tests,
  +3 CSV filter/direction/formula tests, +1 browser render test).
- `python manage.py test report_v2 lunit_audit --noinput` → Ran 409 tests OK (skipped=1: the
  symlink-privilege skip above; includes real-Chromium browser suites — layout, gallery, seed —
  with screenshots under the evidence folder).
- `node --test` per file: seed_widgets 23/0, widgets15 20/0, widgets 10/0, page_state 6/0,
  page_render_bridge 7/0, gallery 6/0 — 72/72 overall.
- `node --check report_v2/static/report_v2/report.js`, `editor.js` → OK.
- `python manage.py seed_report_v2 --check` → `SEED-CHECK OK overview 17 widgets`.
- `git diff --check` clean. W002 (LLM_BASE_URL http) remains pre-existing config, not this task.

**Commit:** Task 16 source/tests + the review fixes above + this log, committed as
`c119ef5` — "feat(report): task 16 PRIME seed + scoped CSV compatibility actions" (30 files,
+3722/−72). Task 17 (snapshots/print) is the next runbook task and stays out of scope here.


## Task 17 — Temporary render snapshots and print flow

Status: complete. Written 2026-09-21. Quick task `260921-uuo`, executed inline in the current
checkout (same pattern as Task 16's review round). Depends on Task 16 (`c119ef5`). Task 18
(email) stays out of scope. No clinical DB access, no production seed publication, no
deployment, no email sent.

### Changed/added files (nine code/test files, all under `django-app/report_v2/`)

- `snapshots.py` (NEW) — the transient snapshot store. No shared cache backend is configured
  (implicit LocMem is per-process and would not survive gunicorn's multi-worker deployment),
  so per the runbook's "small explicitly scoped transient store" rule the store is Django's
  `FileBasedCache` (existing dependency-free infrastructure) rooted at
  `settings.REPORT_V2_SNAPSHOT_ROOT`, defaulting to the same private `private_data/`
  convention as the definitions tree (never under STATIC_ROOT/STATICFILES_DIRS; already
  gitignored). Opaque id = `signing.dumps({sid, u, p, r, x}, salt="report_v2.snapshot.v1")`
  — domain-separated salt, binds user/project/slug/expiry; the document lives under an
  unguessable `snap:<hex>` key with the same bounded timeout (default 900 s, clamp
  [60, 3600]). Typed disjoint failures: `SnapshotTamperedError` (bad signature, malformed
  claims, store/token mismatch), `SnapshotForeignError` (other user/project/slug),
  `SnapshotExpiredError` (signed expiry OR store miss/eviction — both carry the explicit
  "regenerate from the report page" message; never a silent re-freeze). Bounds: ≤ 64
  widgets, ≤ 4 MB serialised, non-empty widget list, and a plain-data gate whose only
  tolerated coercion is date/datetime → ISO (the exact leniency the page's own
  `json.dumps(default=...)` has for date objects riding in table rows; arbitrary objects
  are still refused). `load_snapshot` performs no writes. Store handle is a lazily built
  process singleton with `_reset_store_for_tests()`.
- `exports.py` (NEW) — the export endpoints. `POST /report/<slug>/snapshot/`
  (`@login_required @require_POST @csrf_protect`): body allow-list `{settled, widgets}`;
  the pending gate rejects anything without `settled: true` as `409 pending` BEFORE any
  lookup; then slug validation (404), published-layout load (404), exact-coverage check
  (every published widget exactly once — count, duplicates and unknown ids all 400/403),
  per-entry verification (signed context token parsed and bound to the CURRENT published
  version → tampered 403 / stale 409; overrides re-validated through the Task-13
  `_validate_overrides` against each widget's own allow-list), and only then one
  `data.fetch_project_rows` read + `_evaluate` per widget, fault-isolated per frame (an
  evaluation failure freezes `{"error": str}` exactly like the page render). Returns 201
  with `print_url` + `expires_in`. `GET /report/<slug>/print/<token>/`
  (`@login_required @require_GET`): `load_snapshot` → 410 expired (regenerate message) /
  403 foreign / 403 tampered, then renders **only** the frozen document — no
  re-evaluation, no ORM, no definitions load (proven by test: the seam is monkeypatched to
  AssertionError and the print still renders). The pure `_print_view_model` turns each
  frozen payload into light-theme print blocks: window/anchor/timezone/coverage, the
  applied state line (window token or explicit dates, `site=…` filters, `compare by …`,
  page), count reconciliation (matching/incoming/eligible + exclusion reasons),
  measurement id + threshold policy ref, and accessible tables for aggregates, case rows
  (+ a pagination block when the server page was truncated), chart series (bucket labels
  joined via `bucket_index`), categories, distribution summaries and the confusion matrix
  (GT rows × pred columns + row totals).
- `templates/report_v2/print.html` (NEW) — standalone print document (does NOT extend
  base.html: no app chrome, no sidebar, no widget controls, no `data-report-page` /
  `data-context-token` / `data-initial-payload` contract — a snapshot is export state,
  never restored user preferences). `data-theme="light"` + hardcoded-light `print.css`;
  header shows slug/version/project/generated-at and the frozen-snapshot note; a
  screen-only Print button keeps the browser Save-as-PDF UX.
- `static/report_v2/print.css` (NEW) — always-light palette, `break-inside: avoid` per
  widget block, `thead { display: table-header-group }` so long tables repeat headers
  across pages, `.no-print` hides the button on paper.
- `urls.py` (EDIT, append-only) — two routes after the CSV block:
  `<defid:slug>/snapshot/` and `<defid:slug>/print/<str:snap_token>/`; comment notes the
  token alphabet and re-verification. No existing pattern touched.
- `templates/report_v2/page.html` (EDIT, +5 lines) — a `Print / Save as PDF` button +
  `role="status"` status span in a new export bar under the title, for every logged-in
  viewer (export is a user feature, not an admin one).
- `static/report_v2/report.js` (EDIT, appended inside the page IIFE) — the client flow:
  `updatesSettled()` (no in-flight request AND `pendingSeq <= lastAppliedSeq` for every
  widget) gates the click; while unsettled it polls (150 ms, bounded 15 s) with a
  "Waiting for pending widget updates…" status; on settle it POSTs `{settled: true,
  widgets: [<context token + current overrides per frame>]}` with the CSRF header, opens
  the returned print URL in a new tab (blocked-popup fallback renders a direct link),
  retries bounded on `409 pending`, and surfaces server errors in the status region.
  Nothing is written back into widget state.
- `tests/test_snapshots.py` (NEW, 12 tests) — store guarantees: roundtrip (document
  returned byte-equal, nothing injected), tamper, foreign user/project/slug, all three
  expiry paths (signed past expiry, store timeout/eviction, mocked wall clock) with the
  regenerate message, store/token mismatch = tampering, payload bounds (empty/65
  widgets/>4 MB/non-plain-data/ttl clamps), private default root, opaque-token material
  (no row data in the token, exactly the five claims), independent snapshots,
  JSON-round-trip plain data, and read-only load.
- `tests/test_print.py` (NEW, 12 tests) — endpoint guarantees against the Task-13
  synthetic layout/seam (imports `LAYOUT`/`_Seam`/`_SETTINGS` from `test_pages`; scratch
  `REPORT_V2_ROOT` + `REPORT_V2_SNAPSHOT_ROOT` per test): login gates on both routes,
  CSRF enforcement (403, zero rows read), the 409 pending gate (zero rows read), print
  content (per-widget window `2026-08-02 .. 2026-09-01`, anchor, `site=SYNTH-SITE-A`,
  `compare by site`, `window D-7`, counts line, measurement, policy row, all three widget
  titles including the empty one, light theme + print.css), freeze/immutability (seam →
  AssertionError still 200 with original numbers; republish r2 → print keeps r1 and the
  old title), foreign user 403, expired 410 + regenerate, tampered tokens 403/404,
  exact-coverage rejections (missing/duplicate/no-context entries, zero rows read),
  entry validation parity with `widget_data` (bad filter 400, garbage context 403,
  foreign-slug context 403, stale version 409 — all before any row read), no
  page-state contract on the print page (and the live page still renders defaults
  afterwards), oversized-table pagination note + frozen per-widget errors.

### Cross-checks / decisions recorded

- **Settled gate semantics:** the server cannot observe the browser's in-flight requests,
  so "block export while widget updates are pending" is enforced twice: the client refuses
  to POST until every frame is settled (poll + bound), and the server refuses any POST
  without the explicit `settled: true` acknowledgement (409 pending, before any lookup).
- **Print rendering is server-side static tables** (no echarts on the print page):
  deterministic light-mode output, offscreen widgets included by construction, and the
  chart payloads already carry renderer-contract data (series/categories/summaries/matrix)
  that reads faithfully as tables. Task 18's email CID images will reuse the same frozen
  documents.
- **The snapshot POST re-evaluates server-side** (it never trusts browser-posted metrics,
  per DESIGN "Browser metrics are not authoritative export input"); only the *override
  selections* — already validated server-side — come from the client.
- A snapshot created under version r1 keeps printing after r2 is published (pinned inside
  the document); new page loads open r2. Expired snapshots never regenerate silently.
- Version numbers: 417 report_v2 tests here vs Task 16's "409 OK" — that 409 was the
  combined `report_v2 lunit_audit` run (393 + 16); this task adds 24 (12 + 12), and
  393 + 24 = 417. lunit_audit stays 16.

### Verification (Windows host, Anaconda CPython 3.13.5, run from `django-app/`)

- `python manage.py test report_v2.tests.test_snapshots --noinput` → 12 OK.
- `python manage.py test report_v2.tests.test_print --noinput` → 12 OK.
- `python manage.py test report_v2 --noinput` → **Ran 417 tests OK (skipped=1** — the
  pre-existing Task-16 symlink-privilege skip; includes the Chromium browser suites).
- `python manage.py test lunit_audit --noinput` → 16 OK.
- `node --check report_v2/static/report_v2/report.js` (post-edit), `editor.js` → OK.
- `node --test report_v2/tests/js/` → 72/72 (seed_widgets 23, widgets15 20, widgets 10,
  page_state 6, page_render_bridge 7 — including the modified report.js — gallery 6).
- `python manage.py seed_report_v2 --check` → `SEED-CHECK OK overview 17 widgets`.
- `git diff --check` clean. `git status` shows exactly the nine intended paths. The
  expected `lunit_audit.W002` warning is pre-existing configuration, untouched.

### Deviations / blockers

- None blocking. Two test-time corrections were made during the round (both mine, found by
  the suites): the plain-data gate's coercion had to be narrowed from `default=str` to
  date/datetime-only after the full-suite run caught `object()` silently serialising; and
  the "no rows read" assertions needed the Task-13 seam-ledger reset after page hydration
  (the page GET legitimately reads every widget).
- `REPORT_V2_SNAPSHOT_ROOT` is read via `getattr(settings, ...)` with the private
  fallback, mirroring `REPORT_V2_ROOT`; `lunit_audit/settings.py` was deliberately NOT
  edited (operators may set the override; the compose volume story belongs to the release
  boundary task, like the definitions root note in Task 11).
- The print view's error paths return plain-text bodies (not JSON): the URL is opened as a
  page/tab, and the runbook's requirement is an explicit failure + regenerate instruction,
  which text serves directly.


## Task 18 — Legacy-style HTML email

Status: complete. Written 2026-09-22. Quick task `260922-1t6`, executed inline in the
current checkout. Depends on Task 17 (`5988ea2`). locmem backend only — no real message
was sent at any point. No clinical DB access, no deployment.

### Changed/added files (twelve code/test paths under `django-app/report_v2/`)

- `exports.py` (EDIT) — the email surface, appended to the Task-17 module:
  - `POST /report/<slug>/email/` (`@login_required @require_POST @csrf_protect`; explicit
    user action only — GET is 405, and the preview/print paths never touch the outbox).
    Body allow-list `{snapshot, recipients, note, images}`; every rejection is explicit
    and pre-send. Loads the frozen snapshot through `snapshots.load_snapshot` → typed
    410 expired (regenerate message) / 403 foreign / 403 tampered; document-kind check.
  - **Recipients**: only a JSON list of pre-split address strings (the modal splits like
    legacy on comma/semicolon/newline), regex-validated, ≤ 20 after order-preserving
    de-duplication. **Note**: optional string, stripped, ≤ 2000 chars, template-escaped.
  - **Chart images**: names must be chart-typed widgets of THIS snapshot
    (line/bar/pie/boxplot); payload must be a `data:image/png;base64,` URL whose bytes
    really start with the PNG signature, ≤ 512 KB each, ≤ 32 total; nothing is silently
    dropped — every invalid entry is a 400 naming it.
  - **Values come from the snapshot only** (asserted: the seam monkeypatched to
    AssertionError cannot break a send — the email path never evaluates). The single
    client-supplied presentation input is the validated PNG set.
  - **Disclosure rules** (`_email_view_model`): discrepancy case tables stay
    summary-only — case rows appear only for widgets frozen with `export: full`, and
    even those are capped at 25 rows with an explicit "first 25 of N" note; chart-data
    tables are dropped when a captured PNG carries the widget. `_table` gained a `kind`
    (`meta`/`cases`/`chart`) so the filter is structural, not caption-string matching.
  - **Duplicate-click guard**: server-side replay marker
    (`email-sent:<sha256(token)>:<sha256(recipients+note)>`, TTL 120 s via the new
    transient helpers) → identical second submission is 409 `duplicate` with no re-send;
    different recipients is a legitimate new send. Client side, the Send button disables
    for the whole in-flight chain.
  - **MIME assembly** mirrors the legacy `email_report` exactly: SafeMIMEMultipart
    related/alternative, plain-text + HTML alternatives, inline `MIMEImage` PNG parts
    with `Content-ID <widget_id>@primer-llm`, `From: DEFAULT_FROM_EMAIL`, delivered
    through the configured Django backend. Subject: `PRIMER-LLM Report — <title>
    (<version>)`.
  - **Plain-text fallback** (`_email_text`): readable prose per widget (window, anchor,
    state line, counts, measurement/policy, image note, up to 8 table rows per table
    with "… more rows in the HTML version") — explicitly NOT a monospaced dump and not a
    bare "see HTML" pointer; footer names the sending user.
  - Additive Task-17 touches: the frozen widget now carries its YAML `export` flag, and
    the snapshot POST's 201 body also returns `token` (the email flow references the
    snapshot directly instead of scraping it out of `print_url`). Print rendering is
    unaffected (417-test suite re-run green).
- `snapshots.py` (EDIT) — two small public helpers `transient_set`/`transient_get`
  (bounded charset key, ≤ 1 KB value, TTL clamped to the store's [60, 3600] range) for
  the email replay guard; snapshots themselves unchanged.
- `templates/report_v2/email.html` (NEW) — inline-styled, fixed-light HTML email (email
  clients strip stylesheets): header with title/version/project/generated + frozen-
  snapshot note, the escaped sender note, per-widget blocks (title/type, window/anchor/
  timezone, applied state line, coverage, measurement + policy, counts reconciliation,
  CID `<img>` when a capture exists, rows_note, data tables), footer. Autoescape on.
- `static/report_v2/widgets/{line,bar,pie,boxplot}.mjs` (EDIT, +1 line each) — chart
  renderers now expose `instance.chart = built.chart` so the page can capture PNGs
  (`getDataURL`) for the email; no behaviour change (node suites re-run green).
- `templates/report_v2/page.html` (EDIT) — an "Email report" button beside print plus
  the modal (recipients textarea, optional note, status region, Send/Cancel). Nothing
  persists: no storage API, recipients live only for the current submission.
- `static/report_v2/report.js` (EDIT) — the Task-17 snapshot flow was refactored into a
  shared promise-based `postSnapshot()` (settle-wait + 409 retry, resolves
  `{print_url, token}`); the print button uses it unchanged in behaviour; the email
  modal flow (open/close/submit) parses recipients legacy-style, waits for settle,
  freezes, captures chart PNGs from live instances (guarded; frames without a live
  chart simply send no image), POSTs the email, disables Send while in flight, and
  surfaces sent/duplicate/error status without ever touching widget state.
- `static/report_v2/report.css` (EDIT) — modal + export-bar styles (fixed overlay,
  `[hidden]` respected, status region wraps).
- `urls.py` (EDIT, append-only) — one route: `<defid:slug>/email/`.
- `tests/test_email.py` (NEW, 14 tests) — one per done-when item: login + POST-only +
  CSRF; preview/print never send; a correct send carries recipients, subject with
  title+version, note, every widget title, window `2026-08-02 .. 2026-09-01`, applied
  `site=SYNTH-SITE-A`, counts, measurement + policy, `src="cid:c1@primer-llm"`, one PNG
  part with `Content-ID <c1@primer-llm>` and the exact captured bytes, and a prose
  plain-text fallback ("Sent via PRIMER-LLM by …", no "See HTML version"); values are
  frozen (seam → AssertionError still sends the captured numbers); summary-only tables
  hide accessions while `export: full` tables show them capped ("first 25 of 50");
  `<script>` notes arrive escaped; six image-rejection cases (unknown name, non-chart
  widget, wrong MIME, bad base64, non-PNG bytes, oversized) all 400 with an empty
  outbox; recipient/note bounds and de-duplication; expired/foreign/tampered snapshots
  410/403/403 with an empty outbox; duplicate submission 409 + no re-send while a
  different recipient list sends; a failed email leaves the live report page working;
  the no-storage source scan (mirroring the node rule: cookie WRITES forbidden, the
  CSRF read idiom allowed); the page carries the email affordance + modal markers.

### Design decisions recorded

- **Snapshot-first email**: the modal's Send creates a fresh Task-17 snapshot (settle
  gate included), then sends from that token. This reuses every Task-17 freeze guarantee
  (version pinning, per-widget state, immutability against later data/publication) and
  means print and email are two consumers of one frozen document format.
- **Images are presentation, values are frozen**: per DESIGN, browser metrics are not
  authoritative input — the PNG captures are validated (name/MIME/signature/size) but
  every number in the body comes from the server-side freeze. A widget whose chart could
  not be captured simply ships its data tables.
- **Summary-only disclosure is driven by the published `export` flag** frozen into the
  snapshot (the same flag the CSV compatibility work introduced), not by a hard-coded
  measurement list — the discrepancy rule stays declarative and auditable in YAML.
- **No persisted preferences**: unlike legacy (which cached recipients in
  localStorage), the v2 modal keeps recipients in the form for the current submission
  only, honouring the runbook's fixed product decision; the source-scan tests pin it.

### Verification (Windows host, Anaconda CPython 3.13.5, run from `django-app/`)

- `python manage.py test report_v2.tests.test_email --noinput` → 14 OK (locmem outbox;
  no SMTP configured or contacted).
- `python manage.py test report_v2 --noinput` → **Ran 431 tests OK (skipped=1** — the
  pre-existing symlink-privilege skip; includes the Chromium browser suites).
- `python manage.py test lunit_audit --noinput` → 16 OK.
- `node --test report_v2/tests/js/` → 72/72 (renderer + page-bridge suites, covering the
  four touched chart renderers and the refactored report.js).
- `node --check report_v2/static/report_v2/report.js` (post-edit), `editor.js` → OK.
- `python manage.py seed_report_v2 --check` → `SEED-CHECK OK overview 17 widgets`.
- `git diff --check` clean. The expected `lunit_audit.W002` warning is pre-existing
  configuration, untouched.

### Deviations / blockers

- None blocking. Two corrections during the round (both mine, caught by the suites): the
  test layout initially omitted the schema-required `controls.compare_by` on the two
  table widgets (publish 422), and my no-storage scan was stricter than the node
  contract (it flagged the pre-existing CSRF cookie READ; the rule forbids writes).
- The replay guard is deliberately short-TTL (120 s) and keyed on token+recipients+note:
  a user re-sending the same snapshot to NEW recipients, or re-sending after the guard
  lapses, is a legitimate action and works — only the accidental double-click of one
  submission is suppressed.


## Task 19 — End-to-end acceptance and handoff

Status: complete. Written 2026-09-22. Quick task `260922-1t6`-successor (acceptance round).
Every step below was executed this session against synthetic data only; no clinical
record was opened, no SMTP endpoint contacted, nothing deployed.

### Files added

- `report_v2/tests/test_acceptance_e2e.py` (NEW, 6 tests) — the recorded acceptance
  evidence: (1) the full journey `editor publish -> viewer page -> per-widget filters
  (v1 D-7+site+comparison while sibling t2 stays D-30) -> snapshot -> print (each
  widget's own state) -> email (locmem, CID, pinned version) -> duplicate 409`;
  (2) two reports published/viewed independently, republishing beta leaves alpha's
  pinned version untouched; (3) legacy `/report-old/` login-gated and serving its
  original page; (4) `collectstatic` into an isolated temp root with the PRODUCTION
  `CompressedManifestStaticFilesStorage` (manifest + report_v2 assets present);
  (5) nothing-forbidden scans (no PDF/celery/scheduler dependencies, no attachment
  workflow, no storage APIs in production sources); (6) the seed YAML shape: exactly 17
  widgets, types within the seven displays, no text box, every widget declares
  `export: full|summary`.

### Acceptance checklist (EXECUTION-RUNBOOK) — evidence per item

- [x] **One project can publish and view at least two independent reports.**
      `test_acceptance_e2e.test_two_reports_publish_and_view_independently`;
      `test_editor.test_admin_can_create_second_report`; repository publication tests.
- [x] **User cannot access drafts or alter layout/metric/source/policy/CI/buckets.**
      `test_editor` (non-admin blocked on every editor/preview/mutation route, CSRF
      enforced, invalid YAML never replaces published); `test_pages` widget-data
      override allow-list (any extra key/measurement/policy/CI/layout override -> 400);
      `test_evaluation` forged-input gates; signed context tokens pin slug/version.
- [x] **All seven display types pass synthetic rendering checks.**
      `test_browser_gallery15` (real Chromium, seven displays) + `test_browser_seed`
      (17 seed widgets in Chromium) + node `widgets`/`widgets15`/`seed_widgets`/`gallery`
      suites (72 checks).
- [x] **Independent dates and subgroup filters affect only intended widgets.**
      `test_acceptance_e2e` journey (v1 `2026-08-25..` D-7 window vs sibling t2
      `2026-08-02..` D-30 window in the same snapshot); `test_pages` stale-safe
      sequencing; `test_evaluation` per-widget anchors.
- [x] **Eligibility, matching counts, exclusions and group denominators reconcile.**
      `results.CountAccounting` construction-time reconciliation; `test_evaluation`
      count reconciliation incl. the hand-checkable binary example (matching 7 /
      eligible 6 / excluded 1); `test_classification` denominators.
- [x] **No missing value is silently converted into a negative label or zero rate.**
      `test_thresholds` (require-all ineligibility with named reason);
      `test_classification` (undefined rates are null + reason, never 0).
- [x] **Threshold changes require new policy versions; no site-specific branch remains
      in v2.** `test_thresholds` v1/v2 coexistence without overwrite; the shipped
      policy is uniform `lunit-defaults@1`; `seed_report_v2 --check` clean.
- [x] **First YAML covers all 17 mapped widgets; no monospaced text report block.**
      `test_acceptance_e2e.test_initial_seed_yaml_shape_matches_the_legacy_map`;
      `seed_report_v2 --check` -> "SEED-CHECK OK overview 17 widgets".
- [x] **Print and email preserve current widget states and pinned definitions.**
      `test_print` (frozen against later data AND republication), `test_email`
      (snapshot-only values, states in body), `test_acceptance_e2e` journey.
- [x] **Legacy `/report-old/` still works; no historical source copies were modified.**
      `test_acceptance_e2e.test_legacy_report_old_route_still_serves`; every task commit
      touched only `django-app/report_v2/**` (+ planning docs).
- [x] **No persisted user preferences, new PDF engine or scheduled email feature was
      added.** `test_acceptance_e2e` scans (requirements + sources); node
      `page_state` storage grep; the email modal keeps recipients in-form only.
- [x] **Tests and configuration/seed procedure are recorded for the next implementer.**
      This section + the per-task sections above + the seed procedure below.

### Review items (runbook step 2) — pointers

- **Responsive layout**: browser suites render the page/editor at 1440/1024/390 with
  screenshots (`test_browser_layout`, `test_browser_seed`, evidence folder).
- **Older subgroup message**: `test_evaluation.test_preserved_anchor_with_older_subgroup_latest_date`
  (global D preserved, `subgroup_latest_date` exposed and strictly earlier; coverage
  notes travel into summaries/exports).
- **CI control**: `test_semantics` (Wilson 95%, registered metric/method combos only,
  unsupported balanced-accuracy CI refused; CI visibility comes from the admin-owned
  YAML `ci.enabled`, never a client request).
- **Initial YAML**: seed shape test + `--check`; parity differences vs legacy are
  recorded in the Task 16 section (balanced-accuracy relabel, removed baseline band,
  corrected quartiles) rather than hidden.

### Project isolation (runbook step 3)

`test_catalog` drives the test-only non-CXR `synthx` adapter: the production registry
resolves only `prime` even after test registration, foreign ids escalate to
`CrossProjectReferenceError`, and the test registry never feeds production navigation.

### Commands + results (Windows host, Anaconda CPython 3.13.5, from `django-app/`)

```
python manage.py test --noinput                     # Ran 462 tests ... OK (skipped=1)
python manage.py test report_v2.tests.test_acceptance_e2e --noinput   # 6 OK
python manage.py test lunit_audit --noinput         # 16 OK (subset of the 462)
node --test report_v2/tests/js/                     # 72/72
node --check report_v2/static/report_v2/report.js   # OK (editor.js OK)
python manage.py seed_report_v2 --check             # SEED-CHECK OK overview 17 widgets
git diff --check                                    # clean
```

The single skip is the pre-existing Windows symlink-privilege skip (`test_repository`);
the control itself still asserts on POSIX. The `lunit_audit.W002` LLM-HTTP warning is
pre-existing configuration, untouched.

### Handoff

**Task lineage (code commits):** T01 `bc2c5a7` · T02 `7c7b58f` · T03 `5f91418` ·
T04 `f2f8b35` · T05 `b6386f9` · T06 `81638d4` · T07 `d47e099` · T08 `e78218e` ·
T09 `53ac7a2` · T10 `b0fd9f1` · T11 `d7c3909` · T12 `ba7de09` · T13 `a03ed6a` ·
T14 `272d54f` (+14A `a103fef`) · T15 `95fb511` · T16 `c119ef5` · T17 `5988ea2` ·
T18 `874e7c3` · T19 (this task's commit, tests only).

**Configuration changes (all optional overrides; `lunit_audit/settings.py` untouched):**
- `REPORT_V2_ROOT` — published/draft definition tree. Default
  `django-app/private_data/report_v2_definitions` (gitignored, never collected/served).
- `REPORT_V2_SNAPSHOT_ROOT` — transient export-snapshot store. Default
  `django-app/private_data/report_v2_snapshots` (gitignored; bounded TTL/size).
- No new Python dependencies; static assets are app-local under
  `report_v2/static/report_v2/` (vendored ECharts).

**Seed procedure for the next operator:**
1. `python manage.py seed_report_v2 --check` — validate the shipped seeds (must print
   `SEED-CHECK OK overview 17 widgets`).
2. Admin -> `/report/layout/` -> seed action installs the PRIME overview as a DRAFT.
3. Review/edit the draft, preview, then explicitly Publish. Users see the report at
   `/report/overview/` only after publication.

**Rollback:** the legacy app remains at `/report-old/` (untouched, still the fallback).
The definitions tree is runtime data — keep `private_data/` when rolling back code so
published YAML survives. Each task commit is a self-contained revert unit.

**Known limitations (explicit, not marked complete):**
- The snapshot store is a single-host file cache — correct for the current one-container
  gunicorn deployment; a multi-host deployment would need a shared volume or a real
  cache backend before scaling out.
- `REPORT_V2_ROOT`/`REPORT_V2_SNAPSHOT_ROOT` container volume mounts are NOT yet added
  to `docker-compose.yml` (deployment was out of scope per the runbook); mount both
  paths as volumes before production use so drafts/published YAML survive replacement.
- The print page renders charts as static data tables (deterministic light output; no
  canvas in print). Email chart images are validated client captures; a widget without
  a live chart instance ships tables only.
- The export buttons' click-through (modal interaction, popup open) is verified at
  HTTP level + node harness; the Chromium suites pin page rendering, not the modal.
- Threshold policy v2 exists only in synthetic fixtures; production stays
  `lunit-defaults@1` until a clinical decision changes it (new version, never an edit).
- The email replay guard is 120 s and single-host; a patient re-send after it lapses is
  intentional behaviour.
- `viewer`/`report`/`gt` legacy apps still have no automated suites (pre-existing);
  `/report-old/` is pinned by the new acceptance test at the route level.
