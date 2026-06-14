---
mapped_at: 2026-06-14
focus: concerns
---

# Codebase Concerns

## HIPAA-Relevant Security Gaps

The current application stores and processes ePHI, including patient names, patient IDs, accession numbers, and radiology report text in `CXRStudy` (`django-app/upload/models.py`). The HIPAA work should treat the full Django database, upload/import files, FastAPI task payloads, LLM prompts, LLM responses, and generated exports as ePHI.

## Audit Logging Gap

There is no structured audit logging system for ePHI access. Current logs are console-oriented and implemented with `print()`, `traceback.print_exc()`, and basic Django console logging.

Missing audit coverage includes:

- Viewing studies in `django-app/viewer/views.py`.
- Exporting CSVs from viewer/report/manual GT workflows.
- Editing or deleting studies.
- Uploading/importing PHI-bearing files.
- Fetching FastAPI results.
- Sending report emails.
- LLM prompts and responses in `cxr-audit-api/cxr_audit/lib_audit_cxr_v2.py`.

## Database Risk

The production-style deployment currently uses SQLite in `django-app/lunit_audit/settings.py`. SQLite is stored in a Docker volume and has no built-in user-level access control, network isolation, or database audit capability.

The main PHI-bearing database file is `django-app/db/db.sqlite3` for local development and `django-db` in Docker.

## Transmission Security Risk

External traffic is protected by Nginx TLS in `nginx/nginx.conf`, but internal hops are currently HTTP:

- Nginx to Django: `http://django:8000`.
- Django to FastAPI: `http://api:1221`.
- FastAPI to the OpenAI-compatible LLM endpoint: transport depends on the configured endpoint URL and deployment topology.

TLS, mTLS, or explicit network isolation/authentication is not yet implemented for internal service-to-service traffic.

## Network Segmentation Gap

`docker-compose.yml` defines a single Docker bridge network, `primer-net`, shared by Nginx, Django, and FastAPI. There are no separate public, app, data, and inference networks.

This increases lateral movement risk if any container is compromised.

## Optional API Authentication

FastAPI authentication is bypassed when `API_SECRET_KEY` is empty in `cxr-audit-api/combined_server.py`. Production should fail closed when the key is missing.

## CSRF Gaps

Multiple state-changing Django endpoints are decorated with `@csrf_exempt`, including upload, viewer, and manual GT operations. Examples are in `django-app/upload/views.py`, `django-app/viewer/views.py`, and `django-app/gt/views.py`.

For browser-facing authenticated routes, this is a meaningful CSRF risk.

## CORS Risk

FastAPI uses wildcard CORS with credentials in `cxr-audit-api/combined_server.py`. In the current Compose deployment the API is only exposed to the Docker network, but this configuration is unsafe if the API is ever exposed directly.

## Secrets And Defaults

`django-app/lunit_audit/settings.py` still contains an insecure fallback Django `SECRET_KEY`. `.env.example` contains placeholder defaults such as `change-me-to-a-real-secret-key`, `changeme`, and `dummy`, which are fine as examples but must be enforced against in production.

The real `.env` file was not read during this mapping.

## Container Hardening Gaps

The Dockerfiles use `python:3.11-slim` but still install build tools. Compose has CPU/memory resource limits under `deploy.resources`, but classic local Compose does not always enforce the same way as Swarm unless compatible settings are used.

Current hardening gaps include:

- No read-only root filesystem.
- No `cap_drop: [ALL]`.
- No explicit `security_opt`.
- No image digest pinning.
- No image vulnerability scanning configuration.
- Nginx uses `nginx:alpine` by tag, not digest.

## Task State Fragility

FastAPI stores task state in the process-local `processing_results` dictionary in `cxr-audit-api/combined_server.py`. Django stores background polling state in process-local globals in `django-app/upload/views.py`.

This is fragile across restarts, multiple workers, and horizontal scaling.

## LLM Audit And Privacy Risk

The LLM receives radiology report text through prompt templates in `cxr-audit-api/cxr_audit/prompts.py` and calls in `lib_audit_cxr_v2.py`. There is no prompt/response audit record, hash chain, encrypted prompt store, or model-version attestation.

This is a primary HIPAA concern because every LLM grading call is an ePHI access event.

## Testing Gap

No executable tests were found under the deployed `django/` tree. HIPAA changes will touch security-critical paths and should add tests alongside each phase.

## Data Handling Risk

Repository folders such as `data/`, `data_audit/`, `data_lunit_review/`, `Archive/`, and `RATER dataset/` contain many CSV/XLS/XLSX/parquet files and may contain PHI. Future agents should avoid reading these files unless explicitly required.
