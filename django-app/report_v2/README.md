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
