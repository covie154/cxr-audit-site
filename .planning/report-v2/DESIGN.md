# Extensible clinical AI reports

Status: implementation proposal based on the accepted design interview, 10 September 2026 (Asia/Singapore).
Application implementation is not part of this documentation task.

## Agreed scope

PRIMER monitors clinical AI across projects, not just PRIME CXR. A project owns its datasets,
field mappings, sources, dimensions, measurements, threshold policies and multiple report formats.
First delivery exposes one PRIME project and the existing admin/user distinction. Project membership,
project-admin roles, multi-project navigation and a Koios integration are later work. Do not invent
Koios outcomes or map its data onto CXRStudy. A synthetic second adapter demonstrates extensibility.

Admins edit actual backend YAML, validate, preview and publish. Users can open published reports,
change each widget's dates, permitted cohort filters and one comparison dimension; they cannot alter
layout, metric, sources, thresholds, CI visibility or bucket size. Keep user choices in page memory
only: no localStorage, server preferences or saved dashboards. A fresh visit restores defaults.

Seven displays: value, table, line, bar, pie (optional donut presentation), confusion matrix, box plot.
Use Apache ECharts for charts and semantic HTML for cards/tables. Fixed numeric benchmarks only;
allow named dotted lines on numeric chart axes and target text on cards. No calculated baselines,
alerts, arbitrary formulas, SQL, JavaScript or raw ECharts option objects in YAML.

## Architecture and project boundary

Keep report_v2 independent of the legacy report app. Proposed modules:
- definition schema/loader: parse and validate YAML, resolve project-local identifiers;
- repository: drafts, immutable published files and atomic publication;
- project adapters: explicitly scoped queries and source/dimension definitions;
- measurement registry: requirements, units, valid outputs/displays and computation functions;
- evaluation service: scope -> eligibility -> anchor -> dates -> cohort -> measurement;
- views: authorization, request validation and rendering only;
- frontend widget renderers: consume typed result datasets, separate from ECharts options;
- exports: print HTML and formatted email using the same evaluated widget state.

The PRIME adapter owns CXRStudy mappings; the generic renderer must not name Lunit or CXR columns.
Initially all existing CXRStudy data belongs to the single configured PRIME project. No claim of
multi-project isolation until membership and data ownership are implemented. Pass project context
through every definition, policy, query, cache and export lookup from day one. No global fallback to
another project's source or policy. Future second project activation requires storage and membership
isolation first. Keep SQLite support. Avoid a universal EAV data-store migration in this first release.

## Page and storage proposal

Routes (proposed, not yet implemented):
- /report/: named report list, with a convenient entry for the initial report;
- /report/<report_slug>/: published report;
- /report/layout/: admin report list/create;
- /report/layout/<report_slug>/: YAML editor, errors, draft preview and publish;
- /report-old/: untouched legacy implementation.
Declare reserved admin routes before dynamic report routes. Protect every editor, preview, save and
publish endpoint server-side with the existing admins-group/superuser rule; all viewer/export endpoints
require login. Use CSRF protection for mutations. Future membership checks belong in the project boundary.

Configure a private persistent REPORT_DEFINITIONS_ROOT, separate from public static/media serving:
projects/<project_id>/reports/<report_id>/draft.yaml
projects/<project_id>/reports/<report_id>/versions/<version>.yaml
projects/<project_id>/reports/<report_id>/published.json
projects/<project_id>/policies/<policy_id>/versions/<version>.yaml

IDs resolve through the repository, never user-supplied paths. Validate path containment, duplicate YAML
keys, unknown properties, size/depth limits and project ownership. Disallow custom tags, aliases and
merge keys in the initial loader. Use temporary writes + atomic replacement on the same volume;
optimistic draft revision checks prevent concurrent overwrite. Validate before switching the published
pointer. A failed publication leaves the current version intact. Include persistent-volume deployment
and backup coverage; published YAML must survive container replacement.

An open report pins its published version and referenced immutable policy versions. Publishing changes
only subsequent openings. These versions preserve definitions, not an immutable clinical dataset.
For export parity, retain a short-lived server-owned render snapshot of evaluated results and settings,
scoped to the user/project/report/version. Exports use that snapshot, not a fresh evaluation or untrusted
browser metric values. This is transient export state, not saved user preferences. Expired snapshots
produce an explicit regenerate message. Bound retention and payload sizes using existing infrastructure.
Do not introduce a durable historical report archive or task queue solely for this feature.

## Measurement contract

A measurement declares required fields, eligibility, units, class labels/positive class when relevant,
allowed filters and comparison dimensions, output shape, supported displays and CI methods.
Classification inputs are ground_truth and prediction. Nonclassification inputs use meaningful names
such as value or population, not artificial GT/pred pairs. Source IDs are project-local registered
identifiers, not ORM field paths. Explicit column lists control table output. Registered code implements
complex measurements such as paired-reference comparison; YAML does not execute expressions.

Binary and multiclass confusion matrices declare rows = ground truth, columns = prediction. Multiclass
sensitivity/PPV must specify a target class (one versus rest); do not silently average classes. A fixed
metric table may include several measures, but it has one coherent eligibility population. Specialized
paired-reference tables require all compared inputs and disclose this denominator. LLM-versus-manual
classification names manual as ground_truth and the LLM label as prediction, even though the LLM label
can serve as a reference in another widget. These names express analytic roles, not certainty of truth.

One versioned default threshold per finding; no site overrides and no effective-date switching. A widget
applies its selected policy to all dates/sites. Recompute labels from original scores; do not assume stored
lunit_binarised reflects that version. Never overwrite stored scores or historical labels. Define score
scale, > versus >= and compound-outcome rule explicitly. The example uses legacy > with 0..100 scores,
positive if any configured finding exceeds threshold, but conservatively requires all constituent scores
for a complete aggregate prediction. This completeness rule is a proposal to verify against import schema.
Keep stored operational timing measurements separate: changing a diagnostic threshold must not silently
recalculate historical processing times. A policy never changes metric computation definitions.

Return null plus a reason for undefined metrics, not zero. Distinguish eligible n from a particular metric's
denominator (e.g. actual positives for sensitivity). CI visibility and method are administrator-controlled;
reject unsupported CI requests. Record the chosen statistical method in source metadata and exports.

## Dates, filters and sample size

Each widget independently determines D: latest study/event date with complete inputs for its measurement,
inside project scope and any locked admin cohort, before user subgroup filters. Not ingestion date or wall-clock
today. Timezone comes from the project. Capture D once on initial evaluation; user filter changes do not move
it. Refresh/reopen may advance it. Widgets can therefore have different endpoints; always display dates.
For tables with several metrics, use their common declared eligibility requirement, not a different D per column.

Relative ranges include both endpoints and end at D:
- D: D only; D-7: D minus seven calendar days through D (eight dates).
- W: Monday of D's week; W-1: Monday of the prior week through D.
- M: first of D's month; M-1: first of prior month through D.
- Y: January 1 of D's year; Y-1: January 1 of prior year through D.
- D-n/W-n/M-n/Y-n extend these calendar rules to nonnegative integer offsets.
Resolve relative expressions against D, never today. Explicit user dates remain explicit: do not silently
shift or clamp them; show no eligible observations outside availability. Reject reversed/invalid ranges.
If no eligible row exists, show no eligible data without falling back to today. Line buckets use fixed admin
size (day, Monday-start week, calendar month or year); include and label partial boundary buckets. A missing
rate is a gap, never a zero. A count is zero only when its population and coverage justify it.

Each widget shows dates, active filters and Eligible N / Matching N near its controls. Matching records
satisfy project, admin cohort, dates and user filters before measurement completeness. Exclusions = matching
minus eligible, with non-overlapping reason counts so totals reconcile. Also expose metric-specific denominator
and per-group n. Missing group values form an explicit Unknown group where supported. A scalar/table may expose
filters without supporting comparison; never silently change display type to accommodate an invalid grouping.

A subgroup selection preserves D. Show subgroup's latest eligible date separately when older, e.g.
Coverage 25 Aug-1 Sep; selected subgroup available through 28 Aug. Preview this interaction using synthetic data.
This filter-anchor behavior is provisional UX to assess, not an invitation to silently move the range.

## Layout and export behavior

Proposal: CSS Grid with 12 columns, row-major YAML order, col span 1..12 and minimum height in row units.
No Bootstrap dependency. Tables may grow; never crop clinical rows to meet a fixed height. Stack on narrow
screens. Print in document order with readable chart sizes, repeated table headers and page-break handling.
Five legacy summary cards use spans 2,2,2,3,3 to fit one row; this is a small responsive layout adaptation.

Preserve current Download PDF behavior: POST -> print-ready HTML -> browser Save as PDF/print.
Preserve email modal recipients and optional note, formatted HTML with inline CID chart images and text
fallback. No new PDF engine, attachments workflow or email scheduler. Capture all widgets only after pending
updates complete, including offscreen charts. Version, resolved dates, filters, sources, thresholds, eligible
counts and exclusions travel with every widget. Force a readable light export theme.
Retain legacy CSV actions as scoped compatibility work; detailed case tables use explicit allowed columns
and pagination. Legacy print/email only summarize manual discrepancy cases: keep summary-only handling for
those tables rather than adding full report text to emails. Browser metrics are not authoritative export input;
validate image IDs/content/size against the snapshot and escape all labels and free text.

## Evidence and intentional differences

Legacy sources: report/views.py (_build_report, _compute_metrics, _compute_manual_vs_llm, download_pdf,
email_report); report/templates/report/report.html; report/static/report/report.js and charts.js.
- Existing summary has Total Studies, Graded, Accuracy, Sensitivity, Specificity.
- Existing ROC-AUC field is (sensitivity + specificity)/2. Proposed v2 label: Balanced accuracy;
  real score-based ROC-AUC is a separate measurement requiring a defined score. Do not silently substitute it.
- Existing weekly band is calculated from preceding weekly values. Omit its baseline status banner/band
  under the fixed-reference-only decision. Per-estimate CIs are a separate admin-controlled capability.
- Retain time plots, GT comparison tables, agreement/kappa, McNemar result and discrepancy case tables.
- Remove the monospaced report block from every visible format.
- Initial threshold example copies current defaults only (nodule 15, other findings 10). It is not the user's
  upcoming new threshold selection and is not automatically published.
- New eligibility and null handling can change legacy numbers in addition to threshold changes.

## Glossary

Project: dataset and measurement ownership boundary. Report definition: YAML layout and immutable analytic
choices. Published version: immutable definition selected by a pointer. Widget: independently filtered display.
Source: registered input such as label, score or duration. Measurement: computation and eligibility contract.
Outcome: class vocabulary and positive-class meaning. Policy: immutable per-finding score thresholds.
Cohort: selected record population. Comparison dimension: one grouping variable. Anchor: latest complete event
date before user filters. Snapshot: temporary evaluated view used to keep exports consistent.

## References

ECharts separates datasets and display mappings: https://echarts.apache.org/handbook/en/concepts/dataset/
YAML syntax reference: https://yaml.org/spec/1.2.2/
Balanced accuracy definition: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.balanced_accuracy_score.html
