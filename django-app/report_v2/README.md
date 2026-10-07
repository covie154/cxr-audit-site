# Report v2

Django package: `report_v2`; public route: `/report/`.
The legacy `report` namespace and all its endpoints live at `/report-old/`.

This first increment is an authenticated shell, with no database queries or fabricated metrics.
Add report sections to `templates/report_v2/index.html` and their ECharts options to
`static/report_v2/report.js`. Keep future data aggregation in Python services, separate
from views and presentation. Use Django URL reversal for future endpoints.

Apache ECharts 6.0.0 is vendored locally so report pages do not need a third-party CDN.
Source: https://cdn.jsdelivr.net/npm/echarts@6.0.0/dist/echarts.min.js
Documentation: https://echarts.apache.org/handbook/en/get-started/
The vendor directory includes the upstream LICENSE and NOTICE.


Published cards use **Group by** and **Include groups**. The widget's `controls.compare_by`
and `controls.filters` allow-lists declare supported project dimensions; the project catalog
supplies their labels and the adapter maps their physical fields. Each card has independent
selection state. Changing the field selects all groups; changing dates keeps the selection.
`comparison: ""` explicitly means None, while omitting it uses the widget default.
An empty filter list intentionally matches no records.

`Dimension.bands` defines ordered, non-overlapping half-open ranges `[lower, upper)` as
`(label, lower, upper)` tuples, with `None` for an unbounded endpoint. PRIME configures
Age as <18, 18–39, 40–59, 60–79, 80+, plus Unknown for missing/invalid ages. Boundaries
stay fixed when dates change. Categorical choices come from adapter rows; continuous
choices come from configuration. Group counts remain capped at 100.

Grouped summary tables end in Overall, recomputed from the selected population rather
than averaged across groups. Case tables retain case pagination and have no metric total.
Grouping and group selection are included in frozen print/email snapshots.

The packaged seed enables Site and Age on all 17 cards. Existing published definitions
retain their own allow-lists; re-publish the updated seed to enable these fields there.

Card titles toggle native settings disclosures. Include groups uses a checkbox dropdown next
to Group by; the control row scrolls horizontally on narrow cards. Normal number-card subtext
stays hidden, and table reference text lives inside settings with an accessible table caption.
Range controls select explicit From/To dates or D/W/M/Y presets anchored to the latest complete
eligible study date (D). W starts Monday, M starts on the first and Y on January 1. Window selects
day/week/month/year calendar buckets on time-series cards; it does not alter the date range.
The validated `time_grouping` override is retained in print/email snapshots.

Report navigation lists all published reports for signed-in users. A user may set/clear their own
persistent default; `/report/` opens that report when still published, otherwise the list.
`/report/?list=1` always opens the list, and each report provides an All reports back link.
Default changes require a CSRF-protected POST and a published report identifier. Apply the
report_v2 migration during rollout (`manage.py migrate`) to create the preference table.

`seed/showcase.v1.yaml` provides Showcase: one example of value, table, line, bar, pie,
confusion matrix and horizontal boxplot. It uses the same PRIME adapter and current dataset
as Analysis Report; no alternate data mode is configured. Publish this definition through
the existing editor/repository to make it available in the report list on another deployment.
Categorical cards show the selected grouping's counts, or the configured label distribution
with Group by None. Binary matrices retain both axes for single-class selected populations.
