<!-- GSD:project-start source:PROJECT.md -->

## Project

**PRIMER-LLM HIPAA Compliance**

PRIMER-LLM is a Django and FastAPI medical imaging audit application that processes CARPL CSVs and RIS exports containing chest X-ray report ePHI, grades reports through an OpenAI-compatible LLM endpoint, and stores study-level audit and reporting results. This project cycle hardens the existing `django/` deployment toward HIPAA technical safeguard compliance while preserving the current upload, viewer, report, manual GT, and LLM grading workflows.

**Core Value:** PRIMER-LLM must protect ePHI access, transmission, storage, and auditability without breaking the chest X-ray audit workflow clinicians and auditors already use.

### Constraints

- **Repository boundary**: Only `django/` is a Git repository; planning artifacts and commits must live under `django/.planning/` and `django/.git`.
- **Production data sensitivity**: `CXRStudy`, uploaded files, FastAPI task payloads, generated CSVs, email reports, LLM prompts, and LLM responses may contain ePHI.
- **LLM backend**: Treat the inference service as an OpenAI-compatible endpoint, currently vLLM-compatible; do not assume Ollama-specific runtime behavior even if legacy env var names still contain `OLLAMA_*`.
- **Deployment model**: Docker Compose and Nginx are the current deployment base and should be hardened incrementally rather than replaced wholesale.
- **Database compatibility**: PostgreSQL support must not casually break local development workflows that still use SQLite.
- **Testing**: HIPAA security work must add focused regression coverage for changed controls because the current Django deployment has little executable test coverage.
- **Data access**: Avoid reading or committing PHI-bearing datasets from outside `django/` unless explicitly required.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Primary Application

## Languages And Runtime

- Python is the dominant runtime for both web and analysis tiers.
- Django uses Python 3.11 in `django-app/Dockerfile`.
- FastAPI uses Python 3.11 in `cxr-audit-api/Dockerfile`.
- Frontend behavior is vanilla JavaScript and CSS under app static folders such as `django-app/upload/static/upload/`, `django-app/report/static/report/`, `django-app/viewer/static/viewer/`, and `django-app/gt/static/gt/`.
- Nginx configuration is in `nginx/nginx.conf`.
- Shell startup scripts are used for deployment bootstrap: `django-app/entrypoint.sh` and `nginx/generate-certs.sh`.

## Django Web Tier

- Framework: Django, declared as `Django>=5.0` in `django-app/requirements.txt`.
- The project module is `django-app/lunit_audit/`.
- Local Django apps are `upload`, `viewer`, `report`, and `gt`, registered in `django-app/lunit_audit/settings.py`.
- Static files are served by WhiteNoise via `whitenoise.middleware.WhiteNoiseMiddleware` and `CompressedManifestStaticFilesStorage` in `django-app/lunit_audit/settings.py`.
- Gunicorn is installed during image build in `django-app/Dockerfile` and launched by `django-app/entrypoint.sh`.

## FastAPI Analysis Tier

- Framework: FastAPI 0.104.1 and Uvicorn 0.24.0 are pinned in `cxr-audit-api/api_requirements.txt`.
- The API entry point is `cxr-audit-api/combined_server.py`.
- The analysis pipeline is implemented in `cxr-audit-api/class_process_carpl.py`.
- LLM grading is implemented in `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py` and batched in `cxr-audit-api/cxr_audit/grade_batch_async.py`.
- The API can also run a static upload interface from `combined_server.py`, but Docker deployment runs `combined_server.py --api-only`.

## Data And ML Libraries

- Data processing uses pandas and NumPy in both tiers.
- Metrics use scikit-learn and statsmodels.
- Excel ingestion uses openpyxl, xlrd, and msoffcrypto-tool.
- Matplotlib is included for analysis/plotting.
- LLM calls use the `openai` Python client against an OpenAI-compatible base URL.
- JSON repair support is provided by `json-repair` in the FastAPI dependencies.

## Database

- Current production database configuration is SQLite at `django-app/db/db.sqlite3`, configured in `django-app/lunit_audit/settings.py`.
- Docker mounts SQLite data through the named volume `django-db` in `docker-compose.yml`.
- The main PHI-bearing model is `CXRStudy` in `django-app/upload/models.py`.
- `ProcessingTask` and `UploadedFile` are also defined in `django-app/upload/models.py`.

## Deployment

- `docker-compose.yml` defines three containers: `primer-nginx`, `primer-django`, and `primer-api`.
- Nginx exposes HTTP/HTTPS host ports and proxies to Django over the Docker bridge network.
- Django calls the FastAPI service by hostname `api` and port `1221`.
- The FastAPI service calls an external OpenAI-compatible endpoint through `OLLAMA_BASE_URL`; the variable name is legacy and can point at vLLM or another compatible server.
- Named volumes are `django-db` and `django-media`.

## Dependency Management

- Django dependencies are partially version-bounded with `>=` specifiers in `django-app/requirements.txt`.
- FastAPI dependencies are mixed: FastAPI/Uvicorn/python-multipart are pinned, but many data/ML dependencies are lower-bounded in `cxr-audit-api/api_requirements.txt`.
- There is no lockfile for Python dependencies in `django/`.
- Repository-level `requirements.txt` exists for older or non-Django scripts.

## Build Posture

- Both application Dockerfiles use `python:3.11-slim`.
- Both Dockerfiles install build tools such as `gcc` and `libffi-dev`.
- The FastAPI image switches to `USER appuser`.
- The Django image creates `appuser` but starts as root so `entrypoint.sh` can chown mounted volumes, then uses `su` to run Django commands and Gunicorn as `appuser`.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Python Style

- Module-level constants for thresholds and field maps.
- Helper functions prefixed with `_` for internal view logic.
- Function-based Django views decorated with `@login_required`, `@require_http_methods`, `@csrf_exempt`, and sometimes `@admin_required`.
- Plain `JsonResponse` and `HttpResponse` rather than Django REST Framework serializers.
- Pandas DataFrame transformations for CSV/Excel processing.

## Django View Pattern

- `django-app/upload/views.py` contains upload proxying, task polling, result persistence, and historical import logic.
- `django-app/viewer/views.py` contains queryset filtering, pagination, inline updates, deletes, and CSV export.
- `django-app/report/views.py` contains report computations and export/email endpoints.
- `django-app/gt/views.py` contains manual GT sampling and upload validation.

## Authorization Pattern

- `@login_required` protects general user pages.
- `_is_admin()` checks `user.is_superuser` or membership in the `admins` group.
- `admin_required = user_passes_test(_is_admin)` is duplicated in `upload/views.py` and `viewer/views.py`.
- Viewer database access is admin-only.
- Report and manual GT workflows are login-only.

## Error Handling

- Many views catch broad `Exception` and return `JsonResponse({'error': str(e)})`.
- Several paths call `traceback.print_exc()` or `print()` for server-side diagnostics.
- FastAPI raises `HTTPException` for validation and processing errors.
- Batch LLM processing catches per-report exceptions and substitutes default empty or zero-valued results.

## Logging Pattern

- Django `LOGGING` in `django-app/lunit_audit/settings.py` sends logs to console.
- FastAPI and LLM code use `print()` heavily.
- `CXRClassifier` has a `log_level` parameter, but `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py` contains a TODO to implement it.
- No structured audit logging abstraction exists yet.

## Configuration Pattern

- Django settings read environment variables directly in `django-app/lunit_audit/settings.py`.
- FastAPI and processing code read environment variables directly in `cxr-audit-api/combined_server.py` and `cxr-audit-api/class_process_carpl.py`.
- `.env.example` documents expected variables.

## Data Mapping Pattern

- `save_results_to_database()` in `django-app/upload/views.py` maps API result CSV columns to `CXRStudy`.
- `_IMPORT_COLUMN_MAP`, `_IMPORT_DATETIME_COLS`, and `_IMPORT_TIMEDELTA_COLS` support historical import in `upload/views.py`.
- `FIELD_GROUPS`, `TABLE_COLUMNS`, and filter constants control viewer display and editing in `django-app/viewer/views.py`.

## Frontend Pattern

- Shared shell: `django-app/templates/base.html`.
- Upload UI: `upload/templates/upload/` and `upload/static/upload/`.
- Viewer UI: `viewer/templates/viewer/` and `viewer/static/viewer/`.
- Report UI: `report/templates/report/` and `report/static/report/`.
- Manual GT UI: `gt/templates/gt/` and `gt/static/gt/`.

## Deployment Pattern

## Naming Conventions

- Clinical fields preserve source-system names in CSV processing, often uppercase or title-case.
- Django model fields use snake_case equivalents.
- Lunit pathology columns are mirrored across raw score fields and `_llm` supplemental findings.
- Accession number is the primary identifier throughout, with `accession_no` in Django and `ACCESSION_NO` in CSV/API data.

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Shape

## Django Layers

- `upload`: main file upload, task tracking, FastAPI proxy, historical CSV import.
- `viewer`: admin-only database browser, inline edits, detail view, CSV export, deletion.
- `report`: report generation, metrics, CSV exports, email report, print/PDF HTML.
- `gt`: manual ground truth sample download and label upload.

## Data Model

- Patient identifiers and demographics.
- Study identifiers and procedure timing.
- Lunit score columns.
- Radiologist report text.
- LLM grading output.
- Manual ground truth.
- Supplemental LLM findings.
- Processing metadata.

## Background Processing

- `_start_background_worker()` starts one background polling thread per active task.
- `_background_poll_and_save()` polls FastAPI `/status/{task_id}`.
- `_background_fetch_and_save()` fetches results from `/results/{task_id}` and calls `save_results_to_database()`.

## FastAPI Pipeline

- `/analyze`
- `/analyze-multiple`
- `/analyze-auto-sort`
- `/status/{task_id}`
- `/results/{task_id}`
- `/tasks`
- `/tasks/{task_id}`

## LLM Processing

- Semi-algorithmic extraction and priority scoring.
- Direct LLM grading.
- Hybrid grading.
- LLM-as-judge grading.
- Supplemental Lunit-compatible findings extraction.

## Persistence Boundaries

- SQLite database in `django-app/db/db.sqlite3`, mounted as `django-db`.
- Django media in the `django-media` volume.
- Generated static files in container filesystem.
- FastAPI `processing_results` dictionary in process memory.
- Temporary uploaded files in OS temp directories during analysis.
- Django background thread state in process memory.

## Security Architecture

- `@login_required` for most user-facing pages.
- `@user_passes_test(_is_admin)` for admin-only viewer and task routes.

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
