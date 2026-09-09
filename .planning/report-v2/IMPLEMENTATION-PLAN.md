# Report v2 implementation plan

Status: proposed sequence, not execution authorization. This supplements the current HIPAA roadmap;
it does not renumber, replace or mark its phases complete. Each stage should become a bounded execution plan.

## 1. Definition contract and file repository

Own report_v2/definitions/, configuration, admin routes and focused tests.
Implement strict YAML loading and schema plus semantic validation, project-local catalog resolution,
versioned threshold files, draft preview and atomic publication. Reuse current admin/user access.
Mount a persistent private definitions directory. Keep layout fields separate from measurement inputs.
Acceptance: ordinary users cannot read drafts or mutate/publish via any endpoint; unknown sources, wrong
project refs, duplicate IDs/keys, aliases, bad paths, invalid widths, CI/display mismatch and invalid policies
fail with useful errors. Concurrent saves conflict instead of overwriting. Failed publish preserves current
version. Published files cannot be edited. A valid second report in PRIME can be independently published.

## 2. PRIME adapter, measurements and widget evaluation

Own report_v2/projects/prime.py, measurement registry, dates and evaluation services.
Map CXRStudy without touching clinical data during development. Implement score-derived labels with uniform
thresholds, classification/count/timing measurements, paired-reference comparison and explicit case tables.
Inspect upstream mappings before assigning completeness, score scales and time validity. Use registered
measurements for legacy-specific computations rather than growing a YAML expression language.
Implement eligibility-specific D, fixed anchors during filter interaction, independent windows, one comparison
dimension, matching/eligible counts, reason breakdowns and partial buckets. Add supported CI method explicitly;
do not copy the legacy across-week baseline band. Complete multiclass confusion and per-class measures.
Acceptance: hand-calculated binary and 3-class fixtures, equality-at-threshold, missing scores/GT, unknown
classes, zero denominators, no positives/negatives, paired subsets and duration outliers. Verify D-7's eight
inclusive dates, Monday/week rollover, leap years, month/year rollover, timezone boundaries, older subgroup,
empty project, explicit dates and different widget anchors. Tests must not read development clinical DBs.

## 3. User renderer and all seven display types

Own report_v2 templates/static and typed result payload contract. Keep shared shell changes minimal.
Build named report navigation and registry-based ECharts renderers for line/bar/pie/confusion/box plus HTML
cards/tables. Each widget has dates, allowed filters, comparison selector where supported and sample summary.
Benchmark lines use numeric value axes; multiple fixed targets allowed. CI bars/bands are admin-only and
must be compatible with the measurement. Pin version at opening. No persisted user preferences.
Acceptance: synthetic gallery covers all seven displays, one group variable, multi-filter selection, admin
CI on/off, axis units/benchmark placement, percent/count matrix labels, Unknown group, empty/error/loading
states, responsive widths, accessible data tables, theme switching and resize. Stale responses cannot overwrite
newer filter selections. Refresh restores defaults. Every page request enforces published access.

## 4. Initial PRIME layout and parity review

Use prime-overview.yaml plus policy example as draft seed after stages 1-3, never silently publish.
Match LEGACY-MAP.md; no monospaced box. Keep full-width legacy trend/timing order and manual analysis.
Implement CSV compatibility where needed to keep current actions working under selected widget state.
Acceptance: fixed synthetic data runs through old and new calculations with known equal predictions. Compare
counts and metrics; explicitly account for missing-value corrections, threshold recomputation, balanced-accuracy
label and removed baseline band. Validate timing quantile/whisker convention and case selection semantics.
A second synthetic project adapter must render supported widgets without CXR-specific renderer changes;
it is test-only, not a Koios implementation or production multi-project feature.

## 5. Existing print/email workflows using current widget state

Own report_v2 export service/templates/endpoints and snapshot lifecycle. Reuse existing mail configuration,
recipient/note UX and browser print flow. Do not send live emails in tests; use the in-memory mail backend.
Acceptance: independently altered dates, cohorts and comparison settings in multiple widgets match screen,
print and email. Publishing a new definition/policy while a report is open does not alter its export. Dataset
changes after rendering do not change the captured snapshot. Reject foreign/expired snapshot IDs and unexpected
widget/image IDs. Wait for chart completion; exports include offscreen widgets and handle oversized tables.
Assert correct CID references, text fallback, escaping, no duplicate email submission, and light print output.
Verify current legacy summary-only handling of discrepancy cases; do not add case text to email by default.

## Release boundary and follow-up

Run focused Django service/security tests, synthetic browser flow and print preview checks; retain /report-old/
as fallback. Validate collectstatic and container persistence for definition files. Demonstrate editor->preview
->publish->user filter->print/email with synthetic data before using production datasets.

Later: project membership and project-admin roles; independent real project storage and import pipelines;
Koios mappings/measurements; visual YAML builder. Excluded: personal saved dashboards, runtime formulas,
site-specific thresholds, historical effective-date policy selection, calculated reference lines, intersecting
comparison dimensions, direct PDF generation and scheduled email.

## Implementation facts still to verify (not reopened product decisions)

- Which raw scores and labels are reliably imported, and their scale; do not guess from display alone.
- Statistical CI method per supported metric and quantile/whisker convention for legacy time plots.
- Group dimensions available in the model and their missing-value semantics. Initial YAML permits site only;
  synthetic tests exercise additional dimensions without claiming clinical fields exist.
- Existing case-table authorization/export coverage and current CSV content.
- Snapshot backend choice/retention within existing deployed infrastructure; no new queue requirement.
- Balance the provisional fixed-anchor UX using an older subgroup example in preview.
