# Step-by-step implementation runbook for Qwen/Terra or equivalent

Use this as the execution brief for a capable coding model. It does not depend on a specific model version.
Status: planned, not implemented. Written 10 September 2026. Complete one task at a time; do not generate
all files in one pass or treat a stub as a completed feature.

## Start here

1. Read django/AGENTS.md and honor the required GSD workflow. Work only in the Django repository.
2. Read DESIGN.md, YAML-CONTRACT.md, LEGACY-MAP.md and the example/schema files beside this document.
3. Read git status. Preserve unrelated work. Do not reset, clean or overwrite other edits.
4. Follow tasks below in order. Dependencies can skip ahead only when explicitly satisfied.
5. Before each task, inspect its current files and tests; the paths below are proposed destinations,
   not a claim those modules already exist. Reuse an equivalent implementation rather than duplicating it.
6. Add focused tests for changed production logic. Run those tests before committing the task.
7. Record changed files, test commands/results and any deviation in IMPLEMENTATION-NOTES.md.
8. If a task fails, fix it before advancing. If a required data definition is unknown, document the exact
   blocker; do not fabricate a clinical rule, reduce validation, or substitute hard-coded demo outputs.
9. No deployment, real email sending, production seed publication or clinical DB access is authorized
   by this plan. Synthetic tests use test DBs/temp directories only. Do not migrate a production DB to test.
10. Avoid parallel agents unless explicitly authorized in that implementation session.

## Fixed product decisions: do not reopen or simplify away

One project initially; admin/user access; future projects own separate data and measurements.
Multiple named YAML reports; admin draft/validate/preview/publish; users cannot edit definitions.
All seven display types. Per-widget dates and allowed filters; one comparison dimension at a time.
No saved user settings. Per-measurement latest complete event-date anchor, unchanged by user subgroup filters.
Fixed benchmarks only. Admin controls CI and bucket size. Uniform per-finding versioned thresholds;
no site-specific overrides, no historical threshold switching. Preserve browser Save-as-PDF and HTML email.
Initial report mirrors old sections minus text box, with explicitly documented calculation corrections.

## Validation commands

Run from django/django-app after selecting the intended development Python environment:

```powershell
python manage.py test report_v2 --noinput
python manage.py test report_v2 lunit_audit --noinput
```

After splitting tests into a package, run each task's module using the same test runner. Tests must configure
static storage and secure-redirect settings as existing tests do, and route artifact roots to temporary
folders. The existing LLM HTTP configuration warning is not permission to alter production transport settings.
Inspect database settings first; tests must create isolated test databases. Use locmem mail, never SMTP.
For new JavaScript, run node --check on each non-module file; if using browser ES modules, use a matching
module syntax check and browser tests instead of treating CommonJS parsing errors as code failures.
Run git diff --check before each commit. Browser testing should use the project's available tooling;
if none exists, add one minimal runner and document its install/run command rather than claiming it ran.
Use explicit file lists when staging. GSD planning/summary updates belong inside this repository.

## Task 01: Inventory and lock the implementation contract

Depends on: none.

**Files/responsibility:** Read-only inventory; write .planning/report-v2/IMPLEMENTATION-NOTES.md.

**Steps:**
1. Inspect current report_v2 shell, upload/models.py, report/views.py, report/charts.js, settings, deployment volumes and test conventions.
2. Map actual field names, score scale and operator to the catalog.
3. Confirm current admin rule and mail/print behavior.
4. Record fixture-safe test commands.
5. Do not inspect database contents or change thresholds.

**Done when:** An explicit table maps every seed source/cohort/output to implementation code. Record the two legacy calculation discrepancies (balanced-accuracy label and inconsistent quartiles). No unknown fields silently mapped. Keep operational timing definitions separate from diagnostic threshold changes.

**Commit boundary:** task 01 implementation and focused tests only, plus its GSD log.

## Task 02: Create a test package and deterministic fixtures

Depends on: 01.

**Files/responsibility:** report_v2/tests/; migrate existing report_v2/tests.py into tests/test_routes.py.

**Steps:**
1. Preserve the four existing route/static/auth tests.
2. Add tests/__init__.py and factories.py.
3. Build in-memory records for pure tests and synthetic CXRStudy rows only in Django test databases.
4. Create binary, three-class, timing, missing-field and older-subgroup fixtures; do not write fixtures to the production DB.

**Done when:** Existing report_v2 tests still pass. Fixture seed is fixed. No real accessions, report text or identifiers are used. Verify the hand-calculated examples below before building statistical code.

**Commit boundary:** task 02 implementation and focused tests only, plus its GSD log.

## Task 03: Implement strict YAML parsing and structural schemas

Depends on: 02.

**Files/responsibility:** report_v2/definitions/loader.py, schemas/; tests/test_definitions.py; requirements.txt only if needed.

**Steps:**
1. Copy the reviewed planning schema into app-owned schema data.
2. Add a strict policy schema.
3. Use a maintained YAML parser with safe constructors and explicit duplicate-key detection.
4. Reject aliases, custom tags, merge keys, extra documents, excessive size/depth and nonfinite numbers.
5. Convert parser/schema errors into path-aware editor messages.
6. Do not add executable templates.

**Done when:** Both seed examples parse. Invalid/duplicate/unknown keys and unsafe YAML fail without file writes. A malformed date such as 2026-02-30 is rejected semantically rather than merely matching a regex. Run python manage.py test report_v2.tests.test_definitions.

**Commit boundary:** task 03 implementation and focused tests only, plus its GSD log.

## Task 04: Define the project catalog and access boundary

Depends on: 03.

**Files/responsibility:** report_v2/projects/base.py, prime.py, registry.py; permissions.py; tests/test_catalog.py.

**Steps:**
1. Define small typed metadata structures for sources, outcomes, cohorts, dimensions and measurement signatures.
2. Register one configured PRIME project.
3. Implement require-project-context lookups with no cross-project fallback.
4. Use current admins group/superuser for edit access; authenticated users may view published PRIME reports.
5. Add test-only second project metadata without production navigation.

**Done when:** Unknown project/source IDs fail. Referencing a source from the synthetic other project fails. No CXR field names appear in generic definition parsing. Do not add project membership models in this release.

**Commit boundary:** task 04 implementation and focused tests only, plus its GSD log.

## Task 05: Implement policy evaluation and classification sources

Depends on: 04.

**Files/responsibility:** report_v2/measurements/predictions.py; tests/test_thresholds.py.

**Steps:**
1. Resolve immutable project-local policy ID/version.
2. Validate 0..100 finite raw scores, configured finding coverage and one default per finding.
3. Classify with the explicit gt operator; any finding strictly above threshold is positive, all constituent scores required for complete aggregate prediction.
4. Label-valued sources bypass thresholding.
5. Do not modify CXRStudy.lunit_binarised.

**Done when:** A score equal to threshold is negative; a higher score positive; any missing constituent score produces ineligible aggregate prediction. Two sites with identical scores give identical labels. Version 1 and version 2 can produce different results without overwriting either policy or stored labels.

**Commit boundary:** task 05 implementation and focused tests only, plus its GSD log.

## Task 06: Implement date windows and buckets as pure functions

Depends on: 04.

**Files/responsibility:** report_v2/dates.py; tests/test_dates.py.

**Steps:**
1. Accept captured anchor date and project timezone.
2. Resolve D/W/M/Y offsets and explicit starts/ends.
3. Calendar periods start Monday/first day/January 1.
4. Return inclusive dates and timezone-safe query boundaries.
5. Bucket day/week/month/year independently of selected range; label partial boundaries.
6. Never use date.today as a fallback.

**Done when:** All date examples below pass. Empty eligibility returns no anchor. Filter requests cannot submit a new anchor. Reversed dates fail. Explicit future dates return coverage/empty results rather than moving the requested range.

**Commit boundary:** task 06 implementation and focused tests only, plus its GSD log.

## Task 07: Implement classification measurements

Depends on: 05.

**Files/responsibility:** report_v2/measurements/classification.py; tests/test_classification.py.

**Steps:**
1. Implement binary confusion counts, accuracy, sensitivity, specificity, PPV, NPV, balanced accuracy and predicted-negative fraction.
2. Return numerator/denominator where applicable and null reasons.
3. Add NxN confusion counts with stable declared class order and target-class one-v-rest rates.
4. Reject out-of-vocabulary classes.
5. Build classification_summary from the same primitives.

**Done when:** Hand-calculated fixtures pass; zero denominators never turn into zero estimates. Multiclass rates without target_class fail validation. Balanced accuracy is not labeled ROC-AUC. No arbitrary averaging or clinical score-based ROC-AUC is introduced.

**Commit boundary:** task 07 implementation and focused tests only, plus its GSD log.

## Task 08: Implement count, duration and reference-comparison measurements

Depends on: 07.

**Files/responsibility:** report_v2/measurements/descriptive.py, agreement.py; tests/test_descriptive.py, test_agreement.py.

**Steps:**
1. Implement record_count, label_count, categorical_count and duration_summary.
2. Use one explicit quantile convention, standard Tukey observed-value whiskers and separate P5/P95 summaries.
3. Implement reference agreement/kappa and legacy paired-reference McNemar test on common complete rows.
4. Implement FN/FP case selection with manual as reference and LLM as prediction; paginate separately from aggregates.

**Done when:** Single-value duration, missing/invalid duration and outliers have declared behavior. Undefined kappa is null. Paired counts exclude incomplete pairs consistently. The synthetic FN/FP cases are in the correct direction. Record exact numerical methods and known differences from old outputs.

**Commit boundary:** task 08 implementation and focused tests only, plus its GSD log.

## Task 09: Add admin-controlled confidence intervals and display validation

Depends on: 08.

**Files/responsibility:** measurement metadata and definitions/validation.py; tests/test_semantics.py.

**Steps:**
1. Choose and document a standard per-proportion CI method (proposed Wilson 95%) using existing numerical dependencies where available.
2. Support only explicitly registered metric/method combinations.
3. Classification summaries may omit unsupported CI columns.
4. Reject unsupported balanced-accuracy CI instead of inventing it.
5. Validate display compatibility, inputs, columns, buckets, thresholds, benchmarks/units and allowed grouping.

**Done when:** CI off gives no CI rendering data; CI on gives finite ordered bounds in range for supported proportions. Unsupported combinations fail before publication. Box whiskers are not CI. Numeric benchmarks reject nonnumeric charts and mismatched units. No calculated baseline band.

**Commit boundary:** task 09 implementation and focused tests only, plus its GSD log.

## Task 10: Build widget evaluation and request contract

Depends on: 06,09.

**Files/responsibility:** report_v2/evaluation.py, results.py; tests/test_evaluation.py.

**Steps:**
1. Implement project scope and locked cohort -> completeness -> D capture -> widget window -> user filters -> eligible sample -> grouping/buckets -> measurement.
2. Matching count is before completeness but after filters/dates.
3. Assign mutually exclusive exclusion reasons.
4. Accept only date/filter/single-comparison overrides keyed by published widget IDs.
5. Bound pagination and group cardinality; do not return raw rows for aggregate plots.

**Done when:** Different measurements yield different anchors. Older subgroup preserves D and exposes its actual latest date. Counts reconcile. Invalid IDs or attempts to override measurement/policy/CI/layout fail. Paired tables have a declared common population. All payloads carry sources, versions, dates and unit metadata.

**Commit boundary:** task 10 implementation and focused tests only, plus its GSD log.

## Task 11: Implement file-backed drafts and immutable publication

Depends on: 03,04,09.

**Files/responsibility:** report_v2/definitions/repository.py; settings.py; compose config; tests/test_repository.py.

**Steps:**
1. Add private configurable persistent root; keep sample seeds outside runtime published directories.
2. Implement read/save draft, revision conflict check, validate/preview and immutable publish with atomic pointer update.
3. Validate IDs before path construction and resolved containment.
4. Make publication updates safe across workers using a supported lock or compare-and-swap mechanism.
5. Add test-injected temp root.

**Done when:** Traversal, wrong project, duplicate version, stale revision and invalid YAML are rejected. Failed publication leaves old pointer. Multiple reports publish independently. Container mount survives replacement. Runtime definitions are not served as public media/static files.

**Commit boundary:** task 11 implementation and focused tests only, plus its GSD log.

## Task 12: Build the admin YAML editor

Depends on: 10,11.

**Files/responsibility:** report_v2/admin_views.py, urls.py, templates/report_v2/layout.html, static editor JS/CSS; tests/test_editor.py.

**Steps:**
1. Add reserved /report/layout/ routes before report slug routes.
2. Provide report select/create, YAML textarea, validation errors, save draft, preview and explicit publish.
3. Reuse normal widget renderer in preview when available; initially expose validated preview data.
4. Show dirty state/version conflicts.
5. Read/write all endpoints through admin permission checks and CSRF.

**Done when:** Users cannot access editor, draft preview or mutation endpoints even through direct requests. Invalid YAML does not replace published content. Preview does not publish or send email. Admin can create a second report. Do not add drag-and-drop editing.

**Commit boundary:** task 12 implementation and focused tests only, plus its GSD log.

## Task 13: Build report routing, page state and widget frames

Depends on: 10,11.

**Files/responsibility:** report_v2/views.py, urls.py, templates/report_v2/; static/report_v2/report.js, report.css; tests/test_pages.py.

**Steps:**
1. Keep /report-old/ unchanged.
2. /report/ lists published reports; /report/<slug>/ opens a version-pinned page.
3. Render sections in YAML order on a 12-column responsive grid.
4. Give every widget its independent date/filter controls and eligible/matching summary.
5. Store overrides only in current-page memory.
6. Pin anchor/version in server-issued page context.

**Done when:** Fresh navigation resets defaults. Ordinary users see no draft/configuration controls. Stale async responses cannot replace newer selections; version/anchor cannot be changed through forged input. Empty widgets remain understandable. Long tables grow or paginate without clipping.

**Commit boundary:** task 13 implementation and focused tests only, plus its GSD log.

## Task 14: Implement value, table, line and bar renderers

Depends on: 13.

**Files/responsibility:** static/report_v2/widgets/ value.js, table.js, line.js, bar.js and registry.js; browser tests.

**Steps:**
1. Keep presentation options generated internally from typed result data.
2. Value/table use safe DOM text; line/bar use locally vendored ECharts.
3. Implement unit formatting, group counts, fixed benchmark dotted lines and supported CI rendering.
4. Keep deterministic colors by group.
5. Provide accessible text/table alternatives, resize and theme cleanup.

**Done when:** Synthetic scalar/table/time-series/grouped-bar examples render correctly. Weekly gaps remain gaps. Exactly one comparison dimension is active. Benchmarks are on the numeric axis and scale properly. Chart disposal prevents leaks after replacement. No CDN or new framework is required.

**Commit boundary:** task 14 implementation and focused tests only, plus its GSD log.

## Task 15: Implement pie, confusion matrix and box-plot renderers

Depends on: 14.

**Files/responsibility:** static/report_v2/widgets/ pie.js, confusion.js, boxplot.js; synthetic browser gallery.

**Steps:**
1. Pie uses mutually exclusive category counts; optional donut flag.
2. Confusion matrix uses declared GT rows/pred columns with count or normalized percentage display.
3. Box plots consume server summaries with correctly labeled whiskers and outliers.
4. Export-safe alternative tables support all charts.

**Done when:** All seven displays are covered. Binary 2x2 and multiclass 3x3 labels/counts match fixtures. Zero-denominator normalized rows show unavailable. No benchmark line is drawn on a pie or confusion matrix. The duration reference 300 seconds appears at 5 minutes when axes format minutes.

**Commit boundary:** task 15 implementation and focused tests only, plus its GSD log.

## Task 16: Complete the 17-widget PRIME seed and compatibility actions

Depends on: 08,12,15.

**Files/responsibility:** app-owned draft seed YAML, policy seed, scoped CSV routes; tests/test_seed.py.

**Steps:**
1. Load reviewed planning seed via an explicit admin seed action/management command into drafts only.
2. Validate each measurement ID/source/column.
3. Include all legacy-map entries except text box and calculated baseline band.
4. Add registered categorical_count and confusion_matrix synthetic demo definitions to tests only.
5. Preserve full/FN/FP CSV capabilities with clearly defined widget source/filter state.

**Done when:** 17 seed widgets validate and render against synthetic PRIME data. Discrepancy tables distinguish LLM-vs-manual from Lunit-vs-reference. All five summary cards and timing metadata exist. No site-specific override and no unapproved new threshold. Record reviewed parity differences instead of hiding them.

**Commit boundary:** task 16 implementation and focused tests only, plus its GSD log.

## Task 17: Implement temporary render snapshots and print flow

Depends on: 16.

**Files/responsibility:** report_v2/snapshots.py, exports.py, print template; tests/test_snapshots.py, test_print.py.

**Steps:**
1. Freeze evaluated result data, report/policy versions and widget overrides server-side for export.
2. Scope opaque IDs to user/project and set bounded expiration.
3. Reuse an existing suitable cache/storage backend; if none works across workers, use a small explicitly scoped transient store rather than assuming process memory.
4. Block export while widget updates are pending.
5. Generate print-ready HTML and retain browser print/Save-as-PDF UX.

**Done when:** Every widget exports its own current dates, filters, grouping and metadata. Later data changes or publication do not alter the captured export. Foreign/expired/tampered snapshots fail explicitly. A snapshot is not restored as user preferences. Offscreen charts and long tables print correctly in light mode.

**Commit boundary:** task 17 implementation and focused tests only, plus its GSD log.

## Task 18: Implement legacy-style HTML email

Depends on: 17.

**Files/responsibility:** exports.py, email template, email modal JS; tests/test_email.py.

**Steps:**
1. Reuse configured Django email backend, recipients/note modal and CID images.
2. Read evaluated values from snapshot, not posted browser metrics.
3. Validate allowed image names, MIME content and bounded sizes.
4. Keep case-table export summary-only.
5. Escape free text and provide readable plain text fallback without a monospaced report block.

**Done when:** Use in-memory email backend: no real messages. Assert recipients, note, CID references, source/version/filter metadata and all intended widgets. Duplicate-click prevention and request errors preserve the current report. Email send requires explicit user action, never preview or publication.

**Commit boundary:** task 18 implementation and focused tests only, plus its GSD log.

## Task 19: Run end-to-end acceptance and handoff

Depends on: 18.

**Files/responsibility:** focused regression tests, synthetic browser checks, .planning/report-v2/IMPLEMENTATION-NOTES.md.

**Steps:**
1. Run all report_v2 and affected existing tests, static collection checks in an isolated location, and editor->publish->viewer filters->print/email synthetic flow.
2. Review responsive layout, older subgroup message, CI control and initial YAML.
3. Verify project isolation with the test-only non-CXR adapter.
4. Preserve legacy route behavior and avoid deployment until separately authorized.

**Done when:** Every acceptance checklist below passes with recorded commands. No clinical records viewed or external email sent. Remaining issues are explicit, not marked complete. Handoff includes commit IDs, test results, configuration changes, seed procedure, rollback and known limitations.

**Commit boundary:** task 19 implementation and focused tests only, plus its GSD log.

## Hand-checkable synthetic acceptance cases

### Binary comparison

Six eligible records: GT [1,1,1,0,0,0], prediction [1,1,0,1,0,0].
Expect TP=2, FN=1, FP=1, TN=2; accuracy, sensitivity, specificity, PPV, NPV and balanced accuracy = 2/3.
Predicted-negative fraction = 3/6. Add one row with missing GT inside coverage: matching=7, eligible=6,
excluded=1. This row must not change the metric. Remove all GT positives: sensitivity becomes null,
not zero. Keep group n separate from sensitivity's positive-case denominator.

### Threshold versioning

Two findings with threshold 10, strict >. Scores [10,10] -> negative; [11,10] -> positive;
[11,null] -> ineligible under require-all policy. Version 2 thresholds 12 changes [11,10] to negative.
Assign identical rows to two synthetic sites: labels must remain equal across sites.

### Multiclass

Declared classes A,B,C. GT [A,A,B,B,C,C], prediction [A,B,B,C,C,A].
Expected matrix rows GT / columns prediction: [[1,1,0],[0,1,1],[1,0,1]].
Accuracy=1/2. For class A: TP=1,FN=1,FP=1,TN=3; sensitivity=1/2, specificity=3/4.
Do not label a single unspecified multiclass sensitivity.

### Calendar windows and fixed anchors

Anchor D=2026-09-01 (Tuesday): D-7 starts 2026-08-25; W starts 2026-08-31;
W-1 starts 2026-08-24; M starts 2026-09-01; M-1 starts 2026-08-01;
Y starts 2026-01-01; Y-1 starts 2025-01-01. All end at D, inclusive.
An older subgroup ending 2026-08-28 does not shift these windows. Another widget whose required fields
are complete only through 2026-08-30 gets its own D. Test a newer incomplete row does not advance D.

### Exports/version pinning

Open report version 1. Widget A uses M/site X; widget B uses D-7/site Y with comparison=site.
Change filters and wait until both finish. Publish report version 2 and threshold policy version 2 elsewhere.
Print/email from the open page retains v1, each widget's filters and its evaluated numbers. New navigation
opens v2 with admin defaults. Never silently regenerate an expired snapshot using new definitions.

## Final acceptance checklist

- [ ] One project can publish and view at least two independent reports.
- [ ] User cannot access drafts or alter layout/metric/source/policy/CI/buckets.
- [ ] All seven display types pass synthetic rendering checks.
- [ ] Independent dates and subgroup filters affect only intended widgets.
- [ ] Eligibility, matching counts, exclusions and group denominators reconcile.
- [ ] No missing value is silently converted into a negative label or zero rate.
- [ ] Threshold changes require new policy versions; no site-specific branch remains in v2.
- [ ] First YAML covers all 17 mapped widgets; no monospaced text report block.
- [ ] Print and email preserve current widget states and pinned definitions.
- [ ] Legacy /report-old/ still works; no historical source copies were modified.
- [ ] No persisted user preferences, new PDF engine or scheduled email feature was added.
- [ ] Tests and configuration/seed procedure are recorded for the next implementer.

## Copy-paste handoff prompt

Implement the next incomplete task in .planning/report-v2/EXECUTION-RUNBOOK.md.
Read django/AGENTS.md and the report-v2 design documents first. Follow the required GSD workflow.
Use existing code patterns, work only in the Django repository, preserve unrelated edits, and use synthetic
data only. Do not skip task dependencies or weaken validation to make tests pass. Complete the task's
acceptance checks, record evidence and commit its scoped changes. Report the task number, changed files,
tests and any unresolved blocker. Do not deploy or send real email. Continue to subsequent tasks only
if this execution session explicitly authorizes the entire runbook.
