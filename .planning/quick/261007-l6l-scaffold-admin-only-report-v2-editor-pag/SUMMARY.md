---
status: complete
---
# Report editor navigation

The editor already exists under report_v2 at /report/layout/ with YAML editing, drafts, preview, and explicit publication. Restored discoverability with an admin-only sidebar link and its active state. Reused existing superuser/admins-group authorization. No backend scaffolding needed.

Verification: editor suite 14 tests passed; VisualShellTemplateTests 3 tests passed. Existing environment warnings: HTTP LLM endpoint and missing collected static directory. Tests use synthetic users and temporary definition storage. Preserved unrelated report/date edits.
