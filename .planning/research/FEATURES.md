# Feature Research: PRIMER-LLM HIPAA Compliance

**Researched:** 2026-06-14
**Scope:** Technical controls for the `django/` deployment

## Table Stakes

### Audit Logging

- Audit event schema with timestamp, username, optional user ID, category, final action detail, request route, HTTP method, status/outcome, source IP, and request/task correlation ID.
- `UserSelected` audit category for simple UI clicks and route/button selections.
- Detailed final action strings that include material parameters such as date ranges, report filters, accession/task identifiers, export type, and button/route selected.
- File upload artifact capture: copy uploaded files into an audit artifact directory with timestamp-prepended sanitized filenames, then link the audit event to the stored artifact.
- Successful LLM batch capture: save batch results to CSV in the audit artifact directory, then link the audit event to that CSV.
- Separate audit database from the production data database.
- Append-only audit write path, with code-level protections against update/delete through normal app flows.
- Integrity metadata for events and artifacts, at minimum SHA-256 hashes; hash chaining is preferred.
- Audit coverage for authentication, uploads, imports, viewer access, edits, deletes, exports, reports, email sends, manual GT downloads/uploads, FastAPI task status/results, and LLM batches.

### Transmission Security

- Production Django security settings for HTTPS, secure cookies, proxy SSL header, HSTS, content sniffing protection, and sane referrer policy.
- Nginx TLS posture kept at TLS 1.2 minimum and TLS 1.3 preferred.
- FastAPI service-to-service authentication required in production; no empty `API_SECRET_KEY` fail-open behavior for production.
- OpenAI-compatible endpoint configured with explicit transport expectations.
- Production startup/config check that fails closed for insecure transport or missing secrets when production mode is enabled.

### Network Segmentation

- Compose networks split into public, app, data, and optional inference boundaries.
- Nginx should not be able to reach databases.
- FastAPI should not be able to reach the production application database unless a future design explicitly requires it.
- Database services should not be exposed on host ports by default.
- Network names and comments should make intended traffic flows obvious.

### Container And Software Minimization

- Remove compilers/build tools from runtime images where practical.
- Run services as non-root.
- Drop Linux capabilities and set `no-new-privileges`.
- Use explicit writable mounts and `tmpfs` for temp paths.
- Document each remaining package that is required at runtime.
- Add image scanning and digest pinning as planned follow-up if not feasible in the first pass.

### PostgreSQL And Migration

- Docker-hosted PostgreSQL option for production application data.
- Separate audit database support.
- Environment-driven database selection without breaking SQLite local development.
- Migration plan from SQLite to PostgreSQL with export, restore, validation, rollback, backup, and cutover steps.
- Synthetic migration rehearsal requirements; no PHI-bearing fixture commits.

### Remaining Controls Planning

- Follow-on document that orders remaining HIPAA-related technical work after the first five feature areas.
- Remaining work should include MFA/RBAC, encryption at rest and backup encryption expectations, CSRF cleanup, admin hardening, retention/review workflows, vulnerability scanning, incident-response hooks, asset/network map maintenance, and configuration baselines.

## Differentiators

- Audit review UI for administrators to filter by username, category, accession/task, date range, and artifact presence.
- Control self-check management command that reports production readiness gaps.
- Deployment evidence report summarizing security settings, Compose topology, database mode, and audit sink status.
- Tamper-evident audit chain verification command.

## Anti-Features

- Logging raw PHI into ordinary application logs.
- Storing audit events only in the same mutable application database as production data.
- Treating console logs as the audit record.
- Keeping uploaded audit artifacts directly web-accessible.
- Sending PHI to a cloud LLM endpoint without deployment governance and a BAA where required.
- Making internal mTLS a prerequisite before simpler high-impact controls are in place.

## Dependencies And Complexity

| Feature Area | Complexity | Key Dependencies |
|--------------|------------|------------------|
| Audit logging | High | Multi-database config, artifact root, middleware/decorators, FastAPI audit hooks |
| Transmission security | Medium | Settings refactor, Nginx config, API secret enforcement, deployment envs |
| Network segmentation | Medium | Compose topology, healthchecks, service hostnames |
| Software minimization | Medium | Dockerfiles, runtime write paths, dependency review |
| PostgreSQL support | High | Django settings, Compose services, migrations, backup/restore rehearsal |
| Remaining controls doc | Low | HIPAA spec, research docs, codebase concerns |
