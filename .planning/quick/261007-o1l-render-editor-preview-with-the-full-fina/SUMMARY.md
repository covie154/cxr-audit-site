---
status: complete
---
# Full report card preview

Preview reuses the published report card template, server frame builder and client control initializer. Alternate chart tables retain the published card accessibility styling. Preview includes settings, dates, grouping, group inclusion, Apply, Reset and table pagination. Controls are evaluated against a snapshot of submitted YAML with the same override validators, through the existing admin-only and CSRF-protected endpoint. No preview state is persisted or written back to the textarea. Switching cards disposes previous charts and aborts pending control requests.

Verification: 43 Django editor/page tests passed, including temporary preview controls and rejected overrides before any data fetch. 26 Node editor/report bridge/state tests passed. Live browser checked Specificity by site: chart rendered, alternate text table clipped for accessibility, Apply changed grouping, Reset restored defaults, YAML/revision/dirty state unchanged, no browser errors.

Source files share prior uncommitted editor work and concurrent visual-editor development. Preserve these working-tree changes; commit this task's planning artifacts separately rather than stage another task's source changes.
