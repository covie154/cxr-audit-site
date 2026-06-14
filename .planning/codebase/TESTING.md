---
mapped_at: 2026-06-14
focus: quality
---

# Codebase Testing

## Current Test Surface

The deployed Django tree does not contain committed test modules under `django-app/` or `cxr-audit-api/`.

The docs mention commands:

- `python manage.py test` in `CLAUDE.md`.
- `python -m unittest unittests.py` in `README.md` for the FastAPI backend.

However, no `unittests.py`, `test_*.py`, or `tests.py` files were found under `django/` during mapping.

## Test Frameworks Available

Potential test frameworks from dependencies and stack:

- Django's built-in test runner is available through Django.
- Python `unittest` is available in the standard library.
- FastAPI can be tested with `TestClient`, but no test dependency or test files are currently present.
- Pandas/scikit-learn processing functions can be tested with ordinary unit tests using small synthetic DataFrames.

## Existing Verification By Documentation

The `documentation/` folder contains several security reports and fix notes that act as manual verification history:

- `documentation/security_report_django_280226.md`
- `documentation/security_report_280226.md`
- `documentation/security_plan_208226.md`
- `documentation/documentation_fixes_1_2.md`
- `documentation/documentation_fixes_3_4.md`

These are useful context but are not executable regression tests.

## High-Value Unit Test Targets

For upcoming HIPAA work, the highest-value unit tests are:

- Audit emitter behavior for Django views and FastAPI endpoints.
- Database routing and settings selection for SQLite vs PostgreSQL.
- Security settings in `django-app/lunit_audit/settings.py`.
- API key enforcement in `cxr-audit-api/combined_server.py`.
- Upload column mapping in `save_results_to_database()`.
- Import validation in `_sanitise_row()` and `import_confirm()`.
- Manual GT validation and update logic in `django-app/gt/views.py`.
- LLM audit wrapper behavior around `BatchCXRProcessor` and `CXRClassifier`.

## Integration Test Targets

Important integration tests should cover:

- Login-required behavior for all Django apps.
- Admin-only enforcement for `/view/` and task management endpoints.
- CSRF behavior after removing `@csrf_exempt`.
- Django-to-FastAPI API-key forwarding.
- FastAPI rejection when `API_SECRET_KEY` is required and missing.
- Upload-to-task-to-save workflow using mocked FastAPI responses.
- PostgreSQL-backed migrations once Postgres support is added.

## HIPAA Verification Needs

HIPAA-oriented phases should add verification for:

- Every ePHI access path emits an audit event with user, action, accession or task identifier, timestamp, and source IP where available.
- Audit logs do not accidentally expose raw secrets.
- LLM prompt and response audit records use hashing or encrypted storage as designed.
- TLS and secure-cookie settings are active when `DEBUG=False`.
- Internal service secrets are required in production.
- Docker Compose network segmentation prevents unintended service access.

## Test Data Rules

Tests should use synthetic data only. Avoid committing real accession numbers, patient names, report text, CSV exports, or Excel files from `data/`, `data_audit/`, `data_lunit_review/`, `Archive/`, or `RATER dataset/`.

Synthetic fixtures should include:

- One normal report.
- One abnormal report.
- One critical report.
- One malformed row.
- One duplicate accession.
- One missing required column case.

## Current Gaps

- No executable tests were found in the deployed `django/` app.
- No CI workflow was found under `.github/` for the Django stack during this map.
- No coverage measurement is configured.
- No security regression tests enforce prior security fixes.
- No migration tests exist for the planned SQLite-to-PostgreSQL work.

