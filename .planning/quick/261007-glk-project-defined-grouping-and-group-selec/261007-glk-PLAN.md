# Quick task 261007-glk

Implement agreed report grouping across every card and V1 table appearance.

1. Add validated project-defined continuous bands and adapter dimension mapping; expose permitted field labels and available groups.
2. Replace free-text filters with Group by and Include groups checkboxes on every card; keep independent state, explicit None, all/clear, date persistence and exports.
3. Extend existing evaluator/renderers for labeled grouped values, summary rows, case grouping, pooled Overall rows and empty selection.
4. Match V1 table header, separators and Overall emphasis.
5. Run focused Python/JS and synthetic browser checks, update preview, commit implementation and GSD state.

Decisions: age bands <18, 18–39, 40–59, 60–79, 80+; Unknown for missing/out-of-range. Project configuration owns labels/bounds. Existing project/card allow-lists and group bounds stay enforced. Root Git/.planning authorized earlier by user.
