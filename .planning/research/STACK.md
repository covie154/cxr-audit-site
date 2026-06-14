# Stack Research: PRIMER-LLM HIPAA Compliance

**Researched:** 2026-06-14
**Scope:** `django/` repository only

## Recommended Stack Choices

### Audit Logging

Use a project-owned audit subsystem rather than relying on a generic audit package as the primary source of truth.

Recommended components:

- Custom Django app, likely `audit`, with an `AuditEvent` model.
- Separate Django database alias, likely `audit`, routed through a database router so audit rows do not live in the production application database.
- Append-only write API used by Django views, middleware, model/service operations, and FastAPI callbacks.
- Audit artifact storage rooted in a dedicated mounted directory or volume, separate from ordinary media.
- Hash-chained events or per-event integrity hashes to make post-hoc mutation detectable.
- Tests around the emitter, database routing, artifact persistence, and representative ePHI workflows.

Generic packages such as `django-auditlog` can still help capture ORM changes, but they should not replace the project-owned event schema because PRIMER needs explicit action categories, detailed final action strings, file artifact links, LLM batch artifact links, and cross-service events.

### Audit Database

Use Django multi-database support:

- `default`: production application data, initially SQLite or PostgreSQL depending on deployment mode.
- `audit`: audit event records, separate database name/volume/user where possible.

For local development, the audit database can be a second SQLite file. For Docker deployment, it should be a separate PostgreSQL database or separate PostgreSQL service from the production database. A separate service gives stronger operational separation; a separate database in the same PostgreSQL service is simpler for the first implementation.

### Audit Artifacts

Use a dedicated audit artifact root, for example `AUDIT_ARTIFACT_ROOT`.

Artifact patterns:

- Uploaded PHI files copied into an audit temp/artifact directory with a timestamp prepended to the sanitized filename.
- Successful LLM batch outputs written to CSV with a timestamped filename.
- Audit events store artifact path, SHA-256 hash, MIME/type category, and size.

The artifact root must be treated as ePHI storage. It should not be served directly by Nginx, and downloads should go through authenticated/admin-only Django views later if review access is needed.

### Transmission Security

Recommended first implementation bar:

- Keep external TLS at Nginx and enforce secure Django settings for production.
- Require a non-empty service secret for Django to FastAPI calls in production.
- Explicitly document the OpenAI-compatible endpoint transport expectation: HTTPS or isolated private network with an authenticated endpoint.
- Add fail-closed deployment checks for missing secrets in production.

Recommended later hardening:

- Add internal mTLS when certificate issuance, rotation, trust-store management, and debugging procedures are ready.

Full mTLS is stronger cryptographically, but it adds operational work that can slow the first milestone. Practical isolation plus authenticated service calls gives immediate risk reduction and leaves a clean upgrade path.

### Network Segmentation

Use Docker Compose networks:

- `public`: Nginx exposed to host ports.
- `app`: Nginx to Django and Django to FastAPI.
- `data`: Django to production DB and audit DB.
- `inference`: FastAPI to an in-stack inference service if vLLM is containerized later.

If the OpenAI-compatible endpoint remains external, restrict it through configuration and documented firewall expectations rather than pretending Compose alone can segment it.

### Container Hardening

Continue using slim Python images initially, but split runtime and build concerns:

- Multi-stage builds where practical.
- Runtime images without compilers and build headers.
- Non-root users for Django, FastAPI, and Nginx where image support allows.
- `cap_drop: [ALL]`, `no-new-privileges`, healthchecks, explicit writable mounts, and `tmpfs` for `/tmp`.
- Avoid `read_only: true` until each service has explicit writable paths for temp files, static generation, logs, and caches.

### PostgreSQL

Use Django's `DATABASES` setting to select SQLite for simple local development and PostgreSQL for Docker deployment.

Recommended package:

- Prefer modern `psycopg` if the project can use it cleanly with Django 5.
- Use `psycopg2-binary` only if compatibility or build simplicity makes it necessary.

Docker deployment should include:

- Production PostgreSQL service.
- Audit PostgreSQL database or service.
- Separate credentials for application DB and audit DB.
- Volumes named clearly enough to prevent accidental deletion.

## Technologies To Avoid For v1

- External unmanaged log aggregators for PHI-bearing audit logs.
- Direct Nginx serving of audit artifacts.
- A generic audit package as the only audit record.
- Full mTLS as a blocker for the first internal review milestone.
- Cloud LLM endpoints for PHI unless a BAA and deployment-specific controls exist.

## Research Notes

The HHS Security Rule summary identifies technical safeguards including access controls, audit controls, integrity, person or entity authentication, and transmission security. The same HHS summary also emphasizes documented policies, procedures, and retained documentation. This project should therefore separate code controls from compliance operations and avoid claiming legal completeness from application changes alone.
