# YAML contract v1 (proposed)

The machine-readable structural contract is report.schema.json. prime-overview.yaml is a draft example;
the application does not load it yet. Policy files have their separate fixed shape illustrated by
lunit-defaults.v1.yaml; implementation must create an equally strict policy schema before publishing.

Schema version describes syntax. Published report version is server-owned publication metadata, not an
editable layout field. Policy references use id@version, resolved only within the report's project.
Widget and section IDs must be stable and unique; reordering must not change identity. Title strings are
plain text. YAML order controls reading order. Width is a 12-column span; height is minimum grid rows.
Each widget explicitly declares its window to make per-widget independence obvious. The legacy seed uses
2025-12-12..D; admins can replace starts with M, M-1, D-7, etc. Quote date literals when editing YAML.

Controls list what users may filter/compare, not arbitrary field names. compare_by is a list of allowed
choices; the runtime selection is a single optional string. default_compare_by must belong to that list.
Do not interpret the allowed list as simultaneous grouping. Filters can select multiple values within a
dimension (OR), with AND between dimensions. Initial site choices come from the PRIME adapter.
A value card permits cohort filters but no comparison in the seed; tables/charts explicitly opt in.

query.measurement is a code-registered ID. query.inputs keys and values must match its declared signature.
query.cohort is an immutable project-defined eligibility/population restriction. This seed's
manual_label_present matches the legacy manually annotated subset. Prediction lunit_findings needs the
threshold policy; llm_abnormal used as prediction is already a label and requires none. Durations use
stored duration sources; counts do not require prediction data. Classification returns typed columns.

Seed registry requirements:
- record_count: inputs {}; label_count: value label source.
- accuracy, sensitivity, specificity, balanced_accuracy, classification_summary:
  ground_truth label + prediction; threshold policy for numeric finding scores.
- duration_summary: value duration source, descriptive statistics and box coordinates.
- reference_agreement: ground_truth + prediction labels, agreement and kappa.
- paired_reference_comparison: ground_truth + alternative_reference + prediction on common complete rows.
- false_negatives, false_positives: ground_truth + prediction labels, paginated case rows and aggregate count.
A generic categorical_count measurement is additionally needed for synthetic pie/bar tests, and
confusion_matrix for binary and multiclass displays. Target class is required for multiclass rates.

Structural schema validation is necessary, not sufficient. Semantic validation must enforce:
- existing project-local sources, policies, cohorts, measurements, output columns and group dimensions;
- unique section/widget IDs, valid dates, no mixed relative end other than D;
- compatible measurement/display, numeric axis for benchmarks, matching units and finite numeric values;
- bucket on time-series line charts, no meaningless bucket on scalar widgets;
- policy required only for score-derived prediction, exact configured finding coverage and score bounds;
- CI method registered and valid when enabled; no CI method when disabled;
- no unsupported option keys for a display, no arbitrary HTML/SQL/Python/ECharts configuration;
- comparison default in allowed choices; only one runtime dimension; valid filter values;
- summary export for case tables as in legacy; no implicit disclosure of every model field.

Scalar result: value/unit, eligible_count, matching_count, denominator where applicable, exclusions,
anchor, resolved_window, filters, comparison, sources, policy version and estimate status.
Grouped/series result: same metadata plus typed rows with group, period boundaries, partial flag,
estimate, denominator/n, optional CI low/high and null reason. Tables declare columns; box plots receive
server-computed summary values, not full raw duration arrays. Confusion matrices declare class order and
row/column meaning. Never send clinical case rows to a chart that only needs aggregates.

The old box chart uses indexed quartiles and clipped 1.5-IQR fences, while its summary uses Python
statistics.quantiles. The seed proposes standard Tukey whiskers with one server-computed quantile
convention for chart and summary. Record this intentional consistency correction; retain P5/P95 text.
Do not confuse box whiskers with confidence intervals. Reference line unit is seconds even if the axis
formats minutes. Fixed targets are converted once through the measurement's unit metadata.

Synthetic gallery must cover types not used by the legacy seed, including bar/pie/confusion matrix.
These fixtures belong in automated tests/demo-only development tooling, never the production project data.
