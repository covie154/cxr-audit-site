# Phase 5 Research: PostgreSQL And Migration Plan

## Research Complete

### Primary Findings

- Django 5.2 supports PostgreSQL through `django.db.backends.postgresql`. For new work, use psycopg 3 rather than building around legacy `psycopg2`.
- Django database connection settings can stay in `DATABASES` and be selected through environment variables. This matches the existing `default` plus `audit` database alias pattern.
- The official PostgreSQL Docker image supports first-run initialization from scripts mounted into `/docker-entrypoint-initdb.d/`. This fits the decision to create local/internal-review app and audit databases automatically while leaving production provisioning to DBA/managed database setup.
- `dumpdata` and `loaddata` are useful building blocks, but full migration tooling should also validate migrations, row counts, representative key presence, sampled field equality, audit database availability, sequence reset needs, and post-import smoke checks.

### Codebase Fit

- `django-app/lunit_audit/settings.py` currently hardcodes SQLite for `default` and partially environment-drives only `audit`.
- `lunit_audit.dbrouters.AuditRouter` already routes audit app models to the `audit` database alias, so Phase 5 should preserve the alias and only change how that alias is configured.
- `docker-compose.yml` already has `primer-data`; the Postgres service should attach only to that network and should not publish host ports by default.
- `django-app/requirements.txt` does not include a PostgreSQL driver.
- Phase 4 moved build dependencies to builder stages, so adding psycopg should not reintroduce runtime compiler packages.

### Planning Guidance

- Keep SQLite as the default when `DATABASE_ENGINE` is absent or set to `sqlite`.
- Add explicit PostgreSQL settings for both `default` and `audit` aliases, with separate environment variable prefixes.
- Add Compose support for one PostgreSQL service, one data volume, and an init script that creates app and audit logical databases for internal-review Docker.
- Implement migration tooling as operator-controlled Django management commands or scripts. It must refuse risky defaults, avoid PHI examples, and produce validation evidence.
- Document production cutover as a controlled runbook: backup, rehearsal on synthetic/approved non-PHI data, migrate schemas, export/import, validate, reset sequences, smoke test, freeze/cutover, rollback.

### Known Constraints

- Docker is not available in this agent environment, so plan verification must include structural Compose checks and clear Docker commands for the user to run where Docker exists.
- Django commands must be capped at five minutes during execution.
- The Git worktree has recurring OneDrive `.git/index.lock` behavior; stop at commit boundaries and let the user commit manually.
