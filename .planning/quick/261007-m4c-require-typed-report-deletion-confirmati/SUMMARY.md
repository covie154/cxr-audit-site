---
status: complete
---
# Focused report editor and typed deletion

Delete requires the exact case-sensitive phrase delete this report. Dialog submit stays disabled for empty/incorrect text, resets on opening, and sends confirmation to the server. Server rejects incorrect/missing confirmation before repository access. Existing admin, CSRF, revision and publication conflict checks remain. Catalog Create report appears below all report entries.

Removed template-reset box and obsolete handlers/styles. Templates remain only in the create dialog. Removed report-selection/create toolbar from detail editor; its report ID comes from route-provided data. Header displays Editing: <report title>. New canonical routes are /layout/ and /layout/editor/<report_name>/, with mutations under /layout/actions/. Existing report-v2 endpoints remain compatible, while sidebar, report links, creation responses and form endpoints use the new namespace.

Verification: 39 Django editor/page tests passed, including exact phrase rejection and catalog placement. JavaScript route-bound save regression passed. Chromium tested canonical catalog -> create -> editor active name/no selection or seed box -> live preview -> desktop/mobile fit -> catalog -> typed exact confirmation -> delete disposable report. No browser errors. Existing records were preserved, and the local preview continues using read-only live study data with separate temporary definition storage. Restarted preview with new routes.
