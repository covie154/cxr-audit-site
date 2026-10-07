---
status: complete
---
# Simplified report presentation

Value cards display one primary measure, with no matching/eligible subtext. In-page CSV links removed. Initial payload hydration runs after modules load, so populated values and charts render immediately. Per-site table uses equal-width columns, readable labels and internal scrolling on mobile. Chart fallback tables remain screen-reader accessible and visually hidden. Value cards use two grid rows and numbers do not wrap.

Validation: 7 database-free Django tests and 25 focused JavaScript tests passed. Actual PRIME seed rendered through the real report view using the existing 12 synthetic records: five single values, five charts, no CSV links, equal-width per-site columns and no desktop/mobile page overflow. No clinical data read. Preview stopped after verification.

Implementation commit: db1e1ec.
