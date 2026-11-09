---
status: complete
---
# Visual report exports
Browser print/Save as PDF renders frozen server payloads with the existing web widget registry and ECharts, configured card widths, compact values and safe table fallback. Email uses grid-width presentation tables, formatted scalar cards and combined images for calendar periods. Date/filter/grouping overrides remain temporary; no model or preference changes.

Verification: 46 Django tests passed using local StaticFilesStorage override; 25 JavaScript tests passed. Synthetic Chromium check verified visible percentage card, pie chart and PDF generation. Screenshot contains synthetic data only.

Limits: automated agent API PDF retains script-free table fallback. No real email sent or deployment performed. Existing Dockerfile/entrypoint changes untouched. No commit: instructions restrict commits to django/.git, which is absent; actual repository root is the workspace. Planning artifacts kept in django/.planning.
