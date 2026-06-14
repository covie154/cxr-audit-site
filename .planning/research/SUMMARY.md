# Research Summary: PRIMER-LLM HIPAA Compliance

**Researched:** 2026-06-14

## Key Findings

**Stack:** Keep the existing Django, FastAPI, Nginx, Docker Compose, and OpenAI-compatible LLM shape. Add a project-owned audit subsystem, a separate audit database, a dedicated audit artifact root, production security settings, segmented Compose networks, hardened runtime images, and optional PostgreSQL deployment.

**Table stakes:** Audit events need explicit timestamp, username, category, final action detail, request metadata, artifact links, and integrity metadata. Uploads and successful LLM batches should produce timestamped audit artifacts. Transmission security should combine external TLS, secure Django settings, required production service secrets, and documented LLM endpoint transport expectations. Docker should move toward segmented networks and minimized runtime containers. PostgreSQL support needs an explicit migration and rollback plan.

**Watch out for:** Console logs are not audit logs. Audit data stored only beside mutable production data is too weak. Full mTLS is useful but operationally heavier than the first milestone needs. Network segmentation and read-only containers can break the existing upload/analysis workflow unless write paths and service DNS are checked. Technical controls alone should not be presented as complete HIPAA compliance.

## Recommended Requirement Categories

1. Audit logging.
2. Transmission security.
3. Network segmentation.
4. Container and software minimization.
5. PostgreSQL support and migration planning.
6. Remaining HIPAA controls ordering.

## Recommended Phase Order

### Phase 1: Audit Logging

Implement the audit database, audit event model, audit artifact storage, emitter helpers, Django route coverage, upload artifact capture, successful LLM batch CSV capture, and tests.

### Phase 2: Transmission Security

Harden Django/Nginx production security settings, require FastAPI service authentication in production, and document or validate OpenAI-compatible endpoint transport.

### Phase 3: Network Segmentation

Split Docker Compose into public, app, data, and optional inference networks. Verify only intended services can communicate.

### Phase 4: Software Minimization

Remove avoidable runtime software, harden container execution, document writable paths, and add practical image/container checks.

### Phase 5: PostgreSQL And Migration Plan

Add Docker-hosted PostgreSQL support for production data and audit data, preserve SQLite local development, and write a migration plan covering backup, export/import, validation, rollback, and cutover.

### Phase 6: Remaining HIPAA Controls Plan

Write an implementation-order document for remaining controls, including MFA/RBAC, encryption at rest and backups, CSRF cleanup, admin hardening, retention and audit review, vulnerability scanning, incident response hooks, asset/network map, and configuration baseline management.

## Implementation Bar Recommendation

Use "technical controls for internal review" as the immediate compliance bar. That means controls are implemented, tested, and documented with known limitations. Design each control so it can evolve into a production-ready HIPAA deployment package, which would also require operational evidence, retention and backup procedures, review workflows, incident procedures, and stakeholder signoff.
