---
mapped_at: 2026-06-14
focus: tech
---

# Codebase Integrations

## Internal Service Integrations

The Django app integrates with the FastAPI analysis API over HTTP. The service address is configured in `CXR_API_CONFIG` in `django-app/lunit_audit/settings.py`, with Docker overriding `CXR_API_IP=api` and `CXR_API_PORT=1221` in `docker-compose.yml`.

The Django upload views call FastAPI endpoints using `requests` in `django-app/upload/views.py`. Important calls include:

- `POST /analyze-auto-sort` from `analyze_auto_sort()`.
- `POST /analyze-multiple` from `analyze_multiple()`.
- `GET /status/{task_id}` from `_background_poll_and_save()` and `get_status()`.
- `GET /results/{task_id}` from `_background_fetch_and_save()` and `get_results()`.

## API Authentication

FastAPI API-key authentication is implemented in `cxr-audit-api/combined_server.py` using `APIKeyHeader` and `verify_api_key()`. The shared key comes from `API_SECRET_KEY`.

Django forwards the key with `X-API-Key` from `get_api_headers()` in `django-app/upload/views.py`.

Important behavior: if `API_SECRET_KEY` is empty in FastAPI, `verify_api_key()` allows all requests. That is useful for development but is a HIPAA-relevant deployment risk.

## LLM Integration

The analysis API uses the OpenAI Python client as a generic OpenAI-compatible client. The current backend can be vLLM or any other OpenAI-compatible endpoint. Configuration is in `cxr-audit-api/class_process_carpl.py`:

- `OLLAMA_BASE_URL`, defaulting to `http://localhost:11434/v1`.
- `OLLAMA_MODEL`, a legacy variable name for the served model identifier.
- `OLLAMA_API_KEY`, a legacy variable name for the endpoint API key.
- `OLLAMA_MAX_WORKERS`, defaulting to `8`.

The classifier creates `OpenAI` clients in `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py`. Batch concurrency is handled by `ThreadPoolExecutor` in `cxr-audit-api/cxr_audit/grade_batch_async.py`.

## File Integrations

The system accepts CARPL/Lunit CSV files and GE/RIS Excel files.

- FastAPI saves uploaded files to temporary paths in `save_uploaded_file()` in `cxr-audit-api/combined_server.py`.
- Protected Excel files are opened with `open_protected_xlsx()` in `cxr-audit-api/open_protected_xlsx.py`.
- Django historical imports are handled in `import_preview()` and `import_confirm()` in `django-app/upload/views.py`.
- Manual GT uploads are handled in `validate_upload()` and `apply_gt()` in `django-app/gt/views.py`.

## Email Integration

Report email sending is implemented in `email_report()` in `django-app/report/views.py`. Django email settings are environment-driven in `django-app/lunit_audit/settings.py`, with defaults targeting SMTP over TLS on port 587.

Email output may include PHI-bearing report content depending on the generated report payload. Any production email transport needs a HIPAA-compatible configuration and recipient governance.

## Nginx Integration

Nginx is configured in `nginx/nginx.conf`.

- HTTP redirects to HTTPS.
- HTTPS proxies all app traffic to `http://django:8000`.
- Proxy headers include `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto`.
- TLS protocols are restricted to TLS 1.2 and TLS 1.3.
- HSTS and CSP headers are currently set in Nginx.

## Docker And Host Integration

`docker-compose.yml` uses a single Docker bridge network named `primer-net`. Both Django and FastAPI share this network. The LLM endpoint is external to the Compose stack and is reached through the configured OpenAI-compatible base URL.

## External Services

The principal external services are:

- vLLM or another OpenAI-compatible LLM endpoint.
- SMTP server for report email.
- Docker host storage for `django-db` and `django-media`.
- Browser clients connecting through Nginx HTTPS.

## HIPAA-Relevant Integration Boundaries

- Django to FastAPI currently uses HTTP inside Docker.
- FastAPI to the OpenAI-compatible LLM endpoint may use HTTP depending on deployment configuration.
- SQLite and media volumes store ePHI on host-backed Docker volumes.
- Prompt and response content sent to the LLM endpoint contains radiology report text and must be treated as ePHI.
- Docker network segmentation is not yet present; all three Compose services share `primer-net`.
