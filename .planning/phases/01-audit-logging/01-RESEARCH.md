# Phase 1 Research: Audit Logging

**Phase:** 01-audit-logging
**Researched:** 2026-06-14
**Status:** Ready for planning

## Technical Approach

Build a project-owned Django `audit` app. Use Django multi-database support to route audit models to a second SQLite database in Phase 1, leaving the settings shape ready for PostgreSQL in Phase 5. Keep all audit writes owned by Django in this phase; FastAPI and LLM activity should be audited from Django submission, status/result handling, result CSV capture, and task metadata.

Use an explicit `AuditEvent` model rather than a generic audit package as the primary event source. The model should support readable action strings, structured metadata JSON, artifact references, SHA-256 integrity hashes, request/user/task fields, and the categories selected in context: `UserSelected`, `FileUpload`, `LLMCall`, `LLMSuccess`, and `LLMFailure`.

Audit writes must be non-blocking for user workflows. The emitter should catch failures and log telemetry to normal Python logging without recursively trying to audit its own failure.

## Existing Touchpoints

- `django-app/lunit_audit/settings.py` currently defines one SQLite `default` DB. Add audit DB alias, router, retention settings, and artifact root here.
- `django-app/lunit_audit/urls.py` is the right place to include any audit URLs if a minimal read-only view is chosen instead of admin-only visibility.
- `django-app/upload/views.py` owns upload submission, background polling, result save, historical import, and task actions.
- `django-app/viewer/views.py` owns ePHI view, detail, update, delete, bulk delete, and export.
- `django-app/report/views.py` owns report generation, report exports, email, and print/PDF HTML.
- `django-app/gt/views.py` owns manual GT count, sample download, upload validation, and GT application.
- `django-app/upload/models.py::ProcessingTask` currently lacks initiating-user attribution; adding nullable `initiated_by` fields is the clean way to preserve background actor context.

## Risks And Mitigations

- **PHI in audit rows:** Avoid raw patient names and report text in action strings/metadata. Prefer IDs, field names, counts, hashes, routes, and date ranges.
- **Upload file stream consumption:** Existing upload proxy reads `UploadedFile` streams before forwarding. Artifact capture must either read once and reuse bytes, or reset file pointers safely.
- **Recursive audit failure:** Emitter failure logging must not call the audit emitter.
- **Admin mutability:** Read-only visibility must override add/change/delete permissions for `AuditEvent`.
- **Middleware noise:** Broad `UserSelected` logging of authenticated GET/page interactions can grow quickly. Metadata should stay compact and avoid response bodies.
- **Second SQLite migrations:** Use a database router so audit migrations apply only to the audit database and non-audit migrations do not accidentally create app tables there.

## Recommended Plan Split

1. Audit foundation: app, model, router, settings, admin read-only visibility, and unit tests.
2. Emitter and user-action instrumentation: middleware/decorators/helpers and representative view/export/edit/delete coverage.
3. Upload artifact capture: full copied files, hashes, metadata, import/GT uploads.
4. LLM/result audit: `LLMCall`, `LLMSuccess`, `LLMFailure`, successful result CSV artifacts, background attribution, and regression tests.

## Verification Focus

Automated tests should use synthetic data only and should prove:

- Audit events are routed to the audit DB.
- `AuditEvent` admin is read-only.
- Audit metadata contains no raw patient names/report text in representative cases.
- Audit write failures do not break wrapped user workflows.
- Upload artifacts are timestamped, hashed, and linked.
- LLM/result paths emit the selected categories with initiating user and task ID.
