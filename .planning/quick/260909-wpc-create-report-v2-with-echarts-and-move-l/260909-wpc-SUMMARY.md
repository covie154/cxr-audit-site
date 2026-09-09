---
status: complete
---
# Report v2 foundation

Implemented in 778aaf0. Legacy report and all named endpoints now resolve under /report-old/.
New authenticated report_v2 app serves /report/ with local Apache ECharts 6.0.0,
responsive chart sizing, theme support, and an explicit unconfigured empty state.
Navigation and upload report link open v2; v2 links to the previous report.

Validation: 20 tests passed (report_v2 and lunit_audit); node --check and scoped git diff --check passed.
Existing LLM HTTP transport configuration warning remains. No clinical records inspected.
Browser visual inspection was not performed. Report sections/data integration are future work.
