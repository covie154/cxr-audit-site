# Requirements: PRIMER-LLM HIPAA Compliance

**Defined:** 2026-06-14
**Core Value:** PRIMER-LLM must protect ePHI access, transmission, storage, and auditability without breaking the chest X-ray audit workflow clinicians and auditors already use.
**Compliance Bar:** Technical controls for internal review.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Audit Logging

- [ ] **AUD-01**: User actions are recorded with timestamp, username, category, and final action detail.
- [ ] **AUD-02**: Simple UI selections use audit category `UserSelected` and include the route, button, filter, date range, accession/task identifier, or other material selection details in the final action.
- [ ] **AUD-03**: File uploads use audit category `FileUpload` and record the upload context plus a link to the captured audit artifact.
- [ ] **AUD-04**: Uploaded files are copied into a dedicated audit artifact directory with a timestamp prepended to a sanitized filename before the normal processing flow continues.
- [ ] **AUD-05**: LLM request attempts use audit category `LLMCall` and record safe batch metadata such as task ID, model identifier, endpoint category, accession count, and timestamp without writing raw PHI to ordinary application logs.
- [ ] **AUD-06**: Successful LLM batches use audit category `LLMSuccess`, save successful result rows to a CSV audit artifact, and link the artifact from the audit event.
- [ ] **AUD-07**: Failed LLM batches use audit category `LLMFailure` and record failure metadata sufficient for review without leaking secrets or raw PHI into ordinary application logs.
- [ ] **AUD-08**: Audit events are stored in a separate audit database from production application data.
- [ ] **AUD-09**: Audit events and audit artifacts include integrity metadata such as SHA-256 hashes, with a design path toward tamper-evident hash chaining.
- [ ] **AUD-10**: Representative ePHI workflows emit audit events, including authentication, uploads, imports, viewer access, edits, deletes, exports, reports, email sends, manual GT downloads/uploads, FastAPI result handling, and LLM batches.

### Transmission Security

- [ ] **SEC-01**: Production Django and Nginx settings enforce HTTPS, secure cookies, HSTS, proxy SSL handling, and related browser security headers.
- [ ] **SEC-02**: FastAPI service authentication fails closed in production when the shared service secret is missing or invalid.
- [ ] **SEC-03**: Django-to-FastAPI calls include required service authentication in production.
- [ ] **SEC-04**: OpenAI-compatible endpoint transport expectations are documented and validated where practical, with HTTPS or isolated private authenticated transport required for production-style internal review.
- [ ] **SEC-05**: Internal mTLS is documented as a later production-hardening option with prerequisites rather than blocking the first implementation.

### Network Segmentation

- [ ] **NET-01**: Docker Compose separates services into public, app, data, and optional inference networks.
- [ ] **NET-02**: Nginx is attached only to the networks required to receive browser traffic and proxy to Django.
- [ ] **NET-03**: Production and audit databases are reachable only from intended services and are not exposed on host ports by default.
- [ ] **NET-04**: The upload-to-analysis workflow still works after network segmentation.

### Container And Software Minimization

- [ ] **CONT-01**: Runtime containers remove avoidable build tools, development utilities, and extraneous runtime packages where practical.
- [ ] **CONT-02**: Services run as non-root users where practical.
- [ ] **CONT-03**: Containers drop unnecessary Linux capabilities and set no-new-privileges where practical.
- [ ] **CONT-04**: Required writable paths are documented and mounted explicitly before enabling stricter filesystem hardening.

### PostgreSQL And Migration

- [ ] **DB-01**: Docker deployment can use PostgreSQL for production application data.
- [ ] **DB-02**: Audit logging can use a separate PostgreSQL-backed audit database or database name from production data.
- [ ] **DB-03**: SQLite remains available for simple local development.
- [ ] **DB-04**: Database configuration is environment-driven and documented for Docker deployment.
- [ ] **DB-05**: A SQLite-to-PostgreSQL migration plan covers backup, export/import, migration execution, validation, rollback, and cutover.
- [ ] **DB-06**: Migration validation uses synthetic or approved non-PHI data and checks more than row counts.

### Remaining Controls Planning

- [ ] **PLAN-01**: A follow-on document orders the remaining HIPAA technical controls after the first five feature areas.
- [ ] **PLAN-02**: The remaining-controls document explicitly covers MFA/RBAC, encryption at rest and backup expectations, CSRF cleanup, admin hardening, audit retention/review, vulnerability scanning, incident response hooks, asset/network map maintenance, and configuration baselines.
- [ ] **PLAN-03**: The remaining-controls document separates code-deliverable technical controls from administrative, physical, BAA, and operational evidence items needed for full production HIPAA readiness.

## v2 Requirements

Deferred beyond this milestone.

### Audit Review

- **AUDR-01**: Admin can search and filter audit events by username, category, date range, route, accession/task identifier, and artifact presence.
- **AUDR-02**: Admin can verify audit event and artifact hashes through a management command.

### Production Readiness

- **PROD-01**: Deployment evidence report summarizes security settings, Compose topology, database mode, audit sink status, and known gaps.
- **PROD-02**: Internal mTLS protects service-to-service traffic after certificate issuance, rotation, trust-store, and incident procedures are defined.

## Out of Scope

Explicitly excluded from this milestone.

| Feature | Reason |
|---------|--------|
| Claiming complete HIPAA compliance | This milestone targets technical controls for internal review; full compliance also needs administrative, physical, legal, and operational work. |
| Business Associate Agreements | Legal/vendor governance is required for production HIPAA readiness but is outside the `django/` code implementation. |
| Workforce training and sanctions policy | Administrative safeguards are outside this repository cycle. |
| Physical host/facility controls | The repository cannot implement facility safeguards. |
| Replacing the LLM grading methodology | The milestone hardens the existing workflow rather than changing clinical scoring logic. |
| Migrating non-`django/` research data | Only the `django/` Git repository is in scope. |
| Cloud LLM endpoint for PHI without governance | The target is a controlled OpenAI-compatible endpoint such as vLLM. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUD-01 | TBD | Pending |
| AUD-02 | TBD | Pending |
| AUD-03 | TBD | Pending |
| AUD-04 | TBD | Pending |
| AUD-05 | TBD | Pending |
| AUD-06 | TBD | Pending |
| AUD-07 | TBD | Pending |
| AUD-08 | TBD | Pending |
| AUD-09 | TBD | Pending |
| AUD-10 | TBD | Pending |
| SEC-01 | TBD | Pending |
| SEC-02 | TBD | Pending |
| SEC-03 | TBD | Pending |
| SEC-04 | TBD | Pending |
| SEC-05 | TBD | Pending |
| NET-01 | TBD | Pending |
| NET-02 | TBD | Pending |
| NET-03 | TBD | Pending |
| NET-04 | TBD | Pending |
| CONT-01 | TBD | Pending |
| CONT-02 | TBD | Pending |
| CONT-03 | TBD | Pending |
| CONT-04 | TBD | Pending |
| DB-01 | TBD | Pending |
| DB-02 | TBD | Pending |
| DB-03 | TBD | Pending |
| DB-04 | TBD | Pending |
| DB-05 | TBD | Pending |
| DB-06 | TBD | Pending |
| PLAN-01 | TBD | Pending |
| PLAN-02 | TBD | Pending |
| PLAN-03 | TBD | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 0
- Unmapped: 33

---
*Requirements defined: 2026-06-14*
*Last updated: 2026-06-14 after initial definition*
