---
mapped_at: 2026-06-14
focus: arch
---

# Codebase Structure

## Repository Top Level

The repo contains both deployed application code and research/data-analysis artifacts.

Important top-level locations:

- `django/`: production-oriented Django/FastAPI/Nginx Docker deployment.
- `scripts_audit/`: earlier or parallel CXR audit scripts and notebooks.
- `scripts_lunit_review/`: earlier Lunit review scripts and FastAPI-like utilities.
- `data/`, `data_audit/`, `data_lunit_review/`, `RATER dataset/`, and `Archive/`: datasets and analysis outputs. These may contain PHI or sensitive research data and should not be scanned casually.
- `Docs & Posters/HIPAA.md`: HIPAA technical compliance spec for upcoming work.
- `Docs & Posters/`: papers, presentations, compliance notes, and manuscript materials.

## Django Deployment Folder

`django/` is the main application workspace.

- `README.md`: user-facing deployment and architecture guide.
- `CLAUDE.md`: agent-facing implementation guide.
- `docker-compose.yml`: Compose stack for Nginx, Django, and FastAPI.
- `.env.example`: environment variable template.
- `nginx/`: reverse proxy config and certificate helper.
- `documentation/`: previous security reports, session notes, and fix documentation.
- `django/TODO.md`: short manual TODO list.

## Django App Folder

`django-app/` contains the Django project.

- `manage.py`: Django CLI entry point.
- `Dockerfile`: Django image build.
- `entrypoint.sh`: migrations, collectstatic, superuser creation, and Gunicorn startup.
- `requirements.txt`: Django tier dependencies.
- `lunit_audit/`: Django project settings and root URLs.
- `upload/`: upload, task tracking, API proxy, CSV import, core models.
- `viewer/`: admin database browser and editing.
- `report/`: reporting dashboard, metrics, exports, email, print/PDF HTML.
- `gt/`: manual ground truth sample and upload workflow.
- `templates/`: shared base and login templates.
- `static/`: global static assets.
- `db/`: local SQLite database location.

## FastAPI Folder

`cxr-audit-api/` contains the analysis API.

- `combined_server.py`: FastAPI app, task endpoints, upload sorting, background processing.
- `class_process_carpl.py`: CARPL/RIS processing pipeline and analysis metrics.
- `open_protected_xlsx.py`: encrypted Excel reading helper.
- `api_requirements.txt`: FastAPI tier dependencies.
- `Dockerfile`: API image build.
- `cxr_audit/`: LLM grading package.
- `padchest_op.json`, `padchest_tubes_lines.json`, `diagnoses.json`: medical dictionary configuration.
- `upload_interface.html`: standalone static upload UI used outside the Docker web UI path.

## LLM Grading Package

`cxr-audit-api/cxr_audit/` contains:

- `lib_audit_cxr_v2.py`: `CXRClassifier` and grading methods.
- `grade_batch_async.py`: batch/concurrent processing.
- `prompts.py`: prompt templates and structured response schemas.
- `helpers.py`: parsing and LLM JSON helper utilities.
- `llm_iter.py`: iterative LLM refinement utilities.
- `supplement.py`: supplemental extraction support.
- `async_decorators.py`: async helper decorators.

## Django App Conventions

Each app follows conventional Django layout:

- `views.py` contains most behavior.
- `urls.py` defines app-level routes.
- `apps.py` defines app config.
- `templates/<app>/` contains HTML templates.
- `static/<app>/` contains app-specific JS/CSS.

Most business logic currently lives in view modules rather than service modules. The main exception is data modeling in `upload/models.py` and LLM/data processing in FastAPI modules.

## Files To Treat Carefully

- `.env` should be treated as sensitive and was not read during mapping.
- `django-app/db/db.sqlite3` stores application data and may contain ePHI.
- CSV/XLS/XLSX files under `data*`, `Archive/`, and related dataset folders may contain ePHI.
- `cxr-audit-api/intermediate_llm.csv` and similar intermediate CSV outputs may contain reports or derived PHI.

## Duplicate/Conflict Files

The project contains files ending in `-DESKTOP-FI60PJK.py` or similar. `CLAUDE.md` says these are backup or conflict copies and should generally be ignored during implementation.

