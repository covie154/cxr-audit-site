# Phase 5: PostgreSQL And Migration Plan - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 5-PostgreSQL And Migration Plan
**Areas discussed:** PostgreSQL activation model, audit database topology, migration plan depth, credential and initialization strategy

---

## PostgreSQL Activation Model

| Option | Description | Selected |
|--------|-------------|----------|
| Opt-in Postgres | SQLite stays the default; Docker can enable Postgres through explicit environment variables. | yes |
| Docker defaults Postgres | Compose moves production-style Docker runs to Postgres immediately, while non-Docker local development keeps SQLite. | |
| Postgres only | All supported runs move to Postgres and SQLite becomes migration-source only. | |

**User's choice:** Opt-in Postgres.
**Notes:** Preserve current local development behavior and make PostgreSQL explicit for production-style/internal-review Docker runs.

---

## Audit Database Topology

| Option | Description | Selected |
|--------|-------------|----------|
| Same service, separate DBs | One Postgres service with separate logical databases for app data and audit data. | yes |
| Separate Postgres services | Stronger isolation with separate containers/services, but more operational overhead. | |
| Same DB, separate schema/tables | Simpler but weaker separation than the current audit-database intent. | |

**User's choice:** Same service, separate databases.
**Notes:** Preserve logical separation for audit data while keeping Compose simpler for this phase.

---

## Migration Plan Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Runbook only | Fastest and least code, but more manual risk. | |
| Runbook + validation command | Practical repeatable checks without full migration automation. | |
| Full migration tooling | Export/import/validate tooling plus runbook; higher scope but more repeatable. | yes |

**User's choice:** Full migration tooling.
**Notes:** Tooling should remain bounded and operator-controlled. It should support synthetic or approved non-PHI validation and should not perform unsupervised PHI cutover by default.

---

## Credential And Initialization Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Compose init + production DBA notes | Automatic app/audit DB creation for Docker, documented manual/managed setup for production. | yes |
| Manual setup only | Safest operationally, but harder to test repeatedly. | |
| Fully automated everywhere | Convenient, but poor fit for production credential governance. | |

**User's choice:** Compose init plus production DBA notes.
**Notes:** Compose initialization is for local/internal-review Docker. Production should use DBA-managed or managed-database provisioning and real secret management.

---

## the agent's Discretion

- Exact environment variable names.
- Management command/script names and output format.
- PostgreSQL init script layout.
- Validation checklist structure.

## Deferred Ideas

- Managed production database provisioning, HA/failover, PITR, vault integration, and full operational DBA procedures.
- Removing SQLite support entirely.
- Advanced PostgreSQL tuning such as pooling, replicas, and query-performance work unless needed for first Postgres support.
