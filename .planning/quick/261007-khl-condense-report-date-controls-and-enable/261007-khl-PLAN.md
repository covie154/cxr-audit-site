---
status: planned
---
# Report date expressions and calendar grouping

Confirmed: keep latest eligible study anchor; both boundaries accept ISO dates or D/W/M/Y with nonnegative minus offsets; W is Monday, M/Y first day. Show YAML values until edited; reset restores YAML. Grouping appears on every card, preserves configured buckets, and defaults to Overall when YAML has no bucket. All seven displays must show meaningful grouped results; retain filters, comparisons, anchor, snapshots and exports.

1. Extend shared date-boundary resolution and trust-boundary validation; simplify form and submit state.
2. Reuse existing evaluation and renderers for bounded calendar groups on non-line cards; retain line series bucketing.
3. Add focused synthetic Python/JS regression coverage, run affected suites, record results and commit code/artifacts.

Repository is already the Django Git root (IDE paths and git root agree), so artifacts live in its existing .planning directory. Execute inline per Codex skill adapter.

Follow-up confirmed: display fixed dates as DD-MM-YYYY, accept DD-MM-YYYY or DD/MM/YYYY, and include native date pickers. Keep ISO dates in YAML/internal transport and retain relative expressions. Verify picker/text synchronization and date normalization.
