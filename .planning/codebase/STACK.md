---
mapped_at: 2026-06-14
focus: tech
---

# Codebase Stack

## Primary Application

PRIMER-LLM is a Python medical imaging audit application centered on this `django/` repository. The deployed stack is a Django web UI, a FastAPI analysis API, Nginx TLS termination, Docker Compose orchestration, and an external OpenAI-compatible LLM endpoint such as vLLM.

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
