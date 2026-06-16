# Phase 5: PostgreSQL And Migration Plan - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds PostgreSQL as an opt-in Docker production/internal-review database option for application and audit data, keeps SQLite available for simple local development, and creates bounded SQLite-to-PostgreSQL migration tooling plus a full migration runbook. It must preserve the existing Django/FastAPI/Nginx workflow and respect the Phase 3 network boundary and Phase 4 container hardening decisions.

</domain>

<decisions>
## Implementation Decisions

### PostgreSQL Activation
- **D-01:** PostgreSQL is opt-in through explicit environment configuration; SQLite remains the default for simple local development.
- **D-02:** Docker support should make PostgreSQL easy to enable for production-style/internal-review deployments without forcing it on every local run.
- **D-03:** The planner should preserve a clear SQLite fallback path and avoid making PostgreSQL-only assumptions in ordinary `manage.py` checks/tests unless Postgres env vars are set.

### Audit Database Topology
- **D-04:** Use one PostgreSQL service in Compose with separate logical databases for application data and audit data.
- **D-05:** Keep the audit database as a distinct Django database alias and migration target, matching the existing audit isolation intent.
- **D-06:** Do not collapse audit data into the default app database or a shared schema in this phase.

### Migration Tooling
- **D-07:** Phase 5 should include full bounded migration tooling, not only a paper runbook.
- **D-08:** Migration tooling should be implemented as repeatable Django management-command or script support that can export, import, validate, and report using synthetic or explicitly approved non-PHI data.
- **D-09:** The tooling must not perform unsupervised PHI cutover by default. Production migration still requires operator approval, backups, and controlled execution.
- **D-10:** Validation must go beyond row counts and include schema/migration state, representative key integrity, sampled field comparisons, audit database checks, and application smoke checks where practical.

### Credential And Initialization Strategy
- **D-11:** Compose may use init scripts or equivalent startup configuration to create app and audit databases for local/internal-review Docker runs.
- **D-12:** Production setup should be documented as DBA-managed or managed-database provisioning, not treated as solved by Compose secrets or sample `.env` values.
- **D-13:** No real passwords, API keys, connection strings, or PHI-bearing examples should be written into planning docs, tests, or committed configuration.

### Carry-Forward Constraints
- **D-14:** Database services must attach only to the Phase 3 data network boundary and must not expose host ports by default.
- **D-15:** Phase 4 runtime minimization should be preserved; adding PostgreSQL dependencies should not reintroduce build tools into runtime stages.
- **D-16:** Docker validation can include structural checks when Docker is unavailable locally, but full Compose/database verification should be documented for an environment with Docker.

### the agent's Discretion
- Choose exact environment variable names, helper command names, migration file layout, and validation output format, provided they are clear, documented, and align with existing Django settings patterns.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### GSD Scope And Requirements
- `.planning/PROJECT.md` - Milestone scope, HIPAA technical-control boundary, and project constraints.
- `.planning/REQUIREMENTS.md` - DB-01 through DB-06 and out-of-scope constraints.
- `.planning/ROADMAP.md` - Phase 5 goal, success criteria, and planned work split.

### Prior Phase Decisions
- `.planning/phases/02-transmission-security/02-CONTEXT.md` - No secrets in docs/tests and production fail-closed posture.
- `.planning/phases/03-network-segmentation/03-CONTEXT.md` - Data network boundary and no database host-port exposure by default.
- `.planning/phases/04-container-and-software-minimization/04-CONTEXT.md` - Runtime minimization, writable paths, and Docker verification limits.

### Existing Code And Configuration
- `django-app/lunit_audit/settings.py` - Current SQLite default database, audit database alias, and database router configuration.
- `django-app/lunit_audit/dbrouters.py` - Audit database routing behavior.
- `django-app/audit/models.py` - Audit event model and cross-database user relation constraints.
- `django-app/upload/models.py` - Main PHI-bearing application models.
- `docker-compose.yml` - Compose service topology, networks, and volumes.
- `.env.example` - Environment configuration contract.
- `django-app/requirements.txt` - Django runtime dependencies.
- `django-app/Dockerfile` - Runtime image dependency installation path.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DATABASES` in `django-app/lunit_audit/settings.py`: already defines `default` and `audit`; Phase 5 can extend this rather than introduce a new settings module.
- `DATABASE_ROUTERS = ["lunit_audit.dbrouters.AuditRouter"]`: already preserves audit app routing to the `audit` database alias.
- `docker-compose.yml` networks: `primer-data` already exists and is the correct network for the PostgreSQL service.
- `.env.example`: existing pattern for environment-driven deployment configuration.

### Established Patterns
- SQLite is currently the simple local default.
- Docker service configuration is environment-driven through `.env` plus Compose `environment`.
- Audit logging intentionally uses a separate database alias from application data.
- Verification should avoid depending on Docker when Docker is not available in the local agent environment.

### Integration Points
- PostgreSQL dependency belongs in `django-app/requirements.txt` and the Django runtime image build.
- Database settings belong in `django-app/lunit_audit/settings.py`.
- Compose database service, volumes, networks, and init scripts belong under `docker-compose.yml` and a small supporting directory if needed.
- Migration tooling should live under a Django app management command path so it can run through `python django-app/manage.py ...`.

</code_context>

<specifics>
## Specific Ideas

- Use one PostgreSQL container for internal-review Docker with two logical databases: one for default application data and one for audit data.
- Include tooling substantial enough to support export/import/validation planning, but keep production PHI migration operator-controlled.
- Keep Docker PostgreSQL opt-in so existing lightweight checks and local workflows do not break.

</specifics>

<deferred>
## Deferred Ideas

- Managed production database provisioning, backup encryption implementation, secret vault integration, HA/failover, PITR, and operational DBA procedures are documented expectations but not fully implemented in this phase.
- Replacing SQLite entirely is deferred; SQLite remains supported for simple local development.
- Connection pooling, read replicas, and advanced PostgreSQL performance tuning are deferred unless needed for the first Docker Postgres path.

</deferred>

---

*Phase: 5-PostgreSQL And Migration Plan*
*Context gathered: 2026-06-16*
