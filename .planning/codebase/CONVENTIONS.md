---
mapped_at: 2026-06-14
focus: quality
---

# Codebase Conventions

## Python Style

The codebase uses straightforward Python modules with function-based Django and FastAPI views. There is limited class abstraction outside Django models and the LLM processing classes.

Common patterns:

- Module-level constants for thresholds and field maps.
- Helper functions prefixed with `_` for internal view logic.
- Function-based Django views decorated with `@login_required`, `@require_http_methods`, `@csrf_exempt`, and sometimes `@admin_required`.
- Plain `JsonResponse` and `HttpResponse` rather than Django REST Framework serializers.
- Pandas DataFrame transformations for CSV/Excel processing.

## Django View Pattern

Most Django behavior lives in `views.py` files.

- `django-app/upload/views.py` contains upload proxying, task polling, result persistence, and historical import logic.
- `django-app/viewer/views.py` contains queryset filtering, pagination, inline updates, deletes, and CSV export.
- `django-app/report/views.py` contains report computations and export/email endpoints.
- `django-app/gt/views.py` contains manual GT sampling and upload validation.

This keeps files easy to find but makes `upload/views.py` and `report/views.py` large and multi-responsibility.

## Authorization Pattern

Authentication uses Django's built-in auth decorators.

- `@login_required` protects general user pages.
- `_is_admin()` checks `user.is_superuser` or membership in the `admins` group.
- `admin_required = user_passes_test(_is_admin)` is duplicated in `upload/views.py` and `viewer/views.py`.
- Viewer database access is admin-only.
- Report and manual GT workflows are login-only.

## Error Handling

Error handling is mostly local and pragmatic.

- Many views catch broad `Exception` and return `JsonResponse({'error': str(e)})`.
- Several paths call `traceback.print_exc()` or `print()` for server-side diagnostics.
- FastAPI raises `HTTPException` for validation and processing errors.
- Batch LLM processing catches per-report exceptions and substitutes default empty or zero-valued results.

This convention is convenient for development but should be hardened for PHI production use.

## Logging Pattern

Current logging is minimal.

- Django `LOGGING` in `django-app/lunit_audit/settings.py` sends logs to console.
- FastAPI and LLM code use `print()` heavily.
- `CXRClassifier` has a `log_level` parameter, but `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py` contains a TODO to implement it.
- No structured audit logging abstraction exists yet.

## Configuration Pattern

Configuration is environment-variable driven.

- Django settings read environment variables directly in `django-app/lunit_audit/settings.py`.
- FastAPI and processing code read environment variables directly in `cxr-audit-api/combined_server.py` and `cxr-audit-api/class_process_carpl.py`.
- `.env.example` documents expected variables.

Several defaults are development-friendly and must be made fail-closed for HIPAA production.

## Data Mapping Pattern

CSV and Excel columns are mapped explicitly to model fields.

- `save_results_to_database()` in `django-app/upload/views.py` maps API result CSV columns to `CXRStudy`.
- `_IMPORT_COLUMN_MAP`, `_IMPORT_DATETIME_COLS`, and `_IMPORT_TIMEDELTA_COLS` support historical import in `upload/views.py`.
- `FIELD_GROUPS`, `TABLE_COLUMNS`, and filter constants control viewer display and editing in `django-app/viewer/views.py`.

## Frontend Pattern

The frontend uses server-rendered templates plus app-specific vanilla JS and CSS.

- Shared shell: `django-app/templates/base.html`.
- Upload UI: `upload/templates/upload/` and `upload/static/upload/`.
- Viewer UI: `viewer/templates/viewer/` and `viewer/static/viewer/`.
- Report UI: `report/templates/report/` and `report/static/report/`.
- Manual GT UI: `gt/templates/gt/` and `gt/static/gt/`.

## Deployment Pattern

Dockerfiles are minimal and build directly from each service directory. Compose uses one bridge network and named volumes. The app favors simple local deployment over cloud-native primitives such as managed secrets, managed databases, centralized logging, or queue workers.

## Naming Conventions

- Clinical fields preserve source-system names in CSV processing, often uppercase or title-case.
- Django model fields use snake_case equivalents.
- Lunit pathology columns are mirrored across raw score fields and `_llm` supplemental findings.
- Accession number is the primary identifier throughout, with `accession_no` in Django and `ACCESSION_NO` in CSV/API data.

