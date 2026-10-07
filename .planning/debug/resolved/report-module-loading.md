---
status: resolved
trigger: Report charts remain on Loading after the ponytail sweep
created: 2026-10-08
updated: 2026-10-08
---
# Report module loading

Root cause: Windows MIME registration makes the normal Django static handler serve page_state.mjs as text/plain. The new required reducer import prevents report.js from starting. Browser test settings had a MIME override, masking the application failure.

Evidence: With lunit_audit.settings and django.contrib.staticfiles.views.serve, the reducer response was HTTP 200 text/plain before the fix, then HTTP 200 text/javascript after it. WhiteNoise's own MIME mapping already serves .mjs as JavaScript.

Fix: Register .mjs as text/javascript in ReportV2Config.ready using stdlib mimetypes.add_type. Remove the browser-test MIME workaround so browser tests depend on application setup. No need to duplicate reducers or reinstate legacy renderer code.

Verification: Static-module regression passed under normal application settings. Static regression plus real Chromium renderer and native email startup tests passed (3 tests). git diff --check passed. No production data or email sends were involved.

Scope: This failure was reproduced locally; the user's live URL was not supplied. A running server must reload application startup for the fix to apply.
