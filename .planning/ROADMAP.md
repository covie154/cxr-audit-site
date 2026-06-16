# Roadmap: PRIMER-LLM HIPAA Compliance

## Overview

This milestone hardens the existing `django/` deployment toward HIPAA technical controls for internal review. The roadmap follows the requested control order: create a durable audit trail first, then harden transport, isolate networks, minimize runtime containers, add PostgreSQL with migration planning, and finally document the remaining HIPAA controls that need later implementation or operational ownership.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Audit Logging** - Add separate audit storage, structured events, artifact capture, LLM audit categories, and representative workflow coverage.
- [ ] **Phase 2: Transmission Security** - Enforce production transport posture, service authentication, and OpenAI-compatible endpoint transport expectations.
- [ ] **Phase 3: Network Segmentation** - Split Docker Compose into intended public, app, data, and inference network boundaries.
- [ ] **Phase 4: Container And Software Minimization** - Remove avoidable runtime software and apply practical container execution hardening.
- [x] **Phase 5: PostgreSQL And Migration Plan** - Add Docker-hosted PostgreSQL support and write the SQLite-to-PostgreSQL migration plan. (completed 2026-06-16)
- [ ] **Phase 6: Remaining HIPAA Controls Plan** - Write the follow-on ordering document for remaining HIPAA technical and operational controls.

## Phase Details

### Phase 1: Audit Logging

**Goal**: The application emits structured, reviewable, integrity-aware audit events to a separate audit database, with linked artifacts for file uploads and successful LLM batches.
**Depends on**: Nothing (first phase)
**Requirements**: [AUD-01, AUD-02, AUD-03, AUD-04, AUD-05, AUD-06, AUD-07, AUD-08, AUD-09, AUD-10]
**Success Criteria** (what must be TRUE):

  1. User can perform representative audited actions and each action creates an audit event with timestamp, username, category, and detailed final action.
  2. User file uploads create `FileUpload` audit events and timestamped audit artifacts with integrity metadata.
  3. LLM batch attempts, successes, and failures create `LLMCall`, `LLMSuccess`, and `LLMFailure` audit events with safe metadata.
  4. Successful LLM batches save CSV audit artifacts and link them from audit events.
  5. Audit events are written to a separate audit database from production application data.

**Plans**: 4 plans
Plans:
**Wave 1**

- [ ] 01-01: Audit data model, database routing, settings, migrations, and integrity fields

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02: Django audit emitter, middleware/decorators, user-selection events, and core workflow instrumentation
- [ ] 01-03: File upload artifact capture and audit event linkage

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-04: LLM call/success/failure audit categories, result CSV artifacts, and regression tests

### Phase 2: Transmission Security

**Goal**: Production-style deployments fail closed for insecure transport and unauthenticated service calls while preserving a practical mTLS upgrade path.
**Depends on**: Phase 1
**Requirements**: [SEC-01, SEC-02, SEC-03, SEC-04, SEC-05]
**Success Criteria** (what must be TRUE):

  1. Production Django and Nginx settings enforce HTTPS, secure cookies, HSTS, proxy SSL handling, and browser security headers.
  2. FastAPI rejects unauthenticated production service calls when the shared service secret is missing or invalid.
  3. Django-to-FastAPI production calls include required service authentication.
  4. OpenAI-compatible endpoint transport expectations are documented and validated where practical.
  5. Internal mTLS is documented as a later hardening option with prerequisites.

**Plans**: 3 plans

Plans:

- [ ] 02-01: Django and Nginx production security settings
- [ ] 02-02: FastAPI service authentication fail-closed behavior and Django header forwarding
- [ ] 02-03: OpenAI-compatible endpoint transport validation, documentation, and tests

### Phase 3: Network Segmentation

**Goal**: Docker Compose uses explicit network boundaries that reduce unintended service reachability without breaking the upload-to-analysis workflow.
**Depends on**: Phase 2
**Requirements**: [NET-01, NET-02, NET-03, NET-04]
**Success Criteria** (what must be TRUE):

  1. Compose defines public, app, data, and optional inference networks with clear service membership.
  2. Nginx can proxy to Django but cannot reach production or audit databases.
  3. Production and audit databases are not exposed on host ports by default.
  4. The existing upload-to-analysis path still works after network changes.

**Plans**: 2 plans

Plans:

- [ ] 03-01: Compose network topology and service membership
- [ ] 03-02: Connectivity verification and upload-to-analysis smoke checks

### Phase 4: Container And Software Minimization

**Goal**: Runtime containers are reduced and hardened enough for internal review without breaking required write paths.
**Depends on**: Phase 3
**Requirements**: [CONT-01, CONT-02, CONT-03, CONT-04]
**Success Criteria** (what must be TRUE):

  1. Runtime images no longer include avoidable build tools, development utilities, or extraneous packages where practical.
  2. Django, FastAPI, and Nginx run as non-root users where practical.
  3. Containers drop unnecessary Linux capabilities and set no-new-privileges where practical.
  4. Required writable paths are documented and mounted explicitly before stricter filesystem hardening is applied.

**Plans**: 3 plans

Plans:

- [ ] 04-01: Runtime dependency inventory and Dockerfile minimization
- [ ] 04-02: Non-root execution, capabilities, and no-new-privileges hardening
- [ ] 04-03: Writable path documentation, tmpfs/volume adjustments, and verification

### Phase 5: PostgreSQL And Migration Plan

**Goal**: Docker deployment can use PostgreSQL for production and audit data, while local SQLite remains available and migration is planned before cutover.
**Depends on**: Phase 4
**Requirements**: [DB-01, DB-02, DB-03, DB-04, DB-05, DB-06]
**Success Criteria** (what must be TRUE):

  1. Docker deployment can run with PostgreSQL-backed production application data.
  2. Audit logging can use a separate PostgreSQL-backed audit database or database name.
  3. SQLite remains available for simple local development.
  4. Database settings are environment-driven and documented.
  5. The migration plan covers backup, export/import, execution, validation beyond row counts, rollback, and cutover.

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 05-01: Environment-driven Django database settings and PostgreSQL dependencies

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02: Docker PostgreSQL services, volumes, credentials, and audit database support

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-03: SQLite-to-PostgreSQL migration plan and synthetic validation checklist

### Phase 6: Remaining HIPAA Controls Plan

**Goal**: A follow-on document defines the exact remaining HIPAA controls and implementation order after the first five control areas.
**Depends on**: Phase 5
**Requirements**: [PLAN-01, PLAN-02, PLAN-03]
**Success Criteria** (what must be TRUE):

  1. A remaining-controls document exists and orders the next HIPAA technical controls.
  2. The document explicitly covers MFA/RBAC, encryption at rest and backups, CSRF cleanup, admin hardening, audit retention/review, vulnerability scanning, incident response hooks, asset/network map maintenance, and configuration baselines.
  3. The document separates code-deliverable controls from administrative, physical, BAA, and operational evidence items needed for full production readiness.

**Plans**: 2 plans

Plans:

- [ ] 06-01: Remaining HIPAA technical control inventory and prioritization
- [ ] 06-02: Boundary documentation for operational, administrative, physical, BAA, and production-readiness evidence items

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Audit Logging | 0/4 | Not started | - |
| 2. Transmission Security | 0/3 | Not started | - |
| 3. Network Segmentation | 0/2 | Not started | - |
| 4. Container And Software Minimization | 0/3 | Not started | - |
| 5. PostgreSQL And Migration Plan | 3/3 | Complete    | 2026-06-16 |
| 6. Remaining HIPAA Controls Plan | 0/2 | Not started | - |
