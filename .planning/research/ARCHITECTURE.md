# Architecture Research: PRIMER-LLM HIPAA Compliance

**Researched:** 2026-06-14

## Current Component Boundaries

Current flow:

1. Browser connects to Nginx.
2. Nginx proxies to Django/Gunicorn.
3. Django handles authentication, uploads, viewer, reports, manual GT, and persistence.
4. Django submits analysis jobs to FastAPI.
5. FastAPI processes CARPL/RIS data and calls an OpenAI-compatible LLM endpoint.
6. Django polls FastAPI and stores results in the production data model.

## Target Security Components

### Audit Subsystem

Add a project-owned audit subsystem with these boundaries:

- Django audit emitter used by middleware, decorators, and service functions.
- FastAPI audit helper that can write audit events through a controlled path, likely by calling a Django internal endpoint or writing to the audit database through a narrow module if shared code is introduced.
- Audit database routed separately from production data.
- Audit artifact root for uploaded files and generated LLM result CSVs.
- Optional admin-only audit review UI in a later phase.

The first implementation should avoid making FastAPI directly depend on Django internals. A pragmatic v1 can audit Django-observable events first, then add FastAPI event emission where batch processing and LLM result CSV generation happen.

### Audit Data Flow

User click:

1. Browser request reaches Django.
2. Middleware/decorator derives username, category `UserSelected`, route/button/action detail, and request metadata.
3. Audit emitter writes `AuditEvent` to the audit database.

File upload:

1. Django receives uploaded file.
2. File is copied to the audit artifact root using a timestamp-prepended sanitized filename.
3. SHA-256 hash and artifact metadata are computed.
4. Audit emitter records upload action and artifact link.
5. Normal upload/analysis flow continues.

Successful LLM batch:

1. FastAPI or Django result ingestion identifies a successful batch completion.
2. Batch result rows are written to an audit artifact CSV.
3. SHA-256 hash and artifact metadata are computed.
4. Audit emitter records the LLM batch action, model/endpoint metadata where safe, and artifact link.

### Transmission Data Flow

External:

- Browser to Nginx over HTTPS.
- Nginx forwards proxy headers to Django.
- Django enforces secure cookies and production HTTPS settings.

Internal:

- Nginx to Django over Compose app network.
- Django to FastAPI over Compose app network with required API secret in production.
- FastAPI to OpenAI-compatible endpoint over HTTPS or a documented isolated private network.

### Network Topology

Recommended Compose topology:

- `public`: host-exposed Nginx only.
- `app`: Nginx, Django, FastAPI.
- `data`: Django, production DB, audit DB.
- `inference`: FastAPI and optional in-stack vLLM service.

PostgreSQL services should only attach to `data`. Nginx should not attach to `data`. FastAPI should not attach to `data` unless an explicit future design requires direct persistence.

### PostgreSQL Architecture

Use environment-driven settings:

- `DATABASE_ENGINE=sqlite|postgres`
- `DATABASE_URL` or explicit PostgreSQL host/name/user/password variables for production data.
- `AUDIT_DATABASE_URL` or explicit audit DB variables for audit data.

The migration plan should treat audit DB setup and production data DB migration separately. Audit logging can start writing new events before historical production data is migrated.

## Suggested Build Order

1. Audit data model, database router, artifact root, and emitter.
2. Audit coverage for Django routes and uploads.
3. LLM batch artifact CSV generation and audit event linkage.
4. Production transmission settings and fail-closed service authentication.
5. Compose network segmentation.
6. Docker image/runtime minimization.
7. PostgreSQL option and migration plan.
8. Remaining HIPAA controls ordering doc.

This order matches the user's requested sequence while making dependencies explicit.
