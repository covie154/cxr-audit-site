---
phase: 05-postgresql-and-migration-plan
plan: 03
subsystem: migration-tooling
tags: [django, migration, postgres, validation, documentation]
requirements-completed: [DB-05, DB-06]
completed: 2026-06-16
---

# Phase 5 Plan 03: SQLite-To-PostgreSQL Migration Tooling Summary

## Outcome

Added operator-controlled Django management commands for migration preparation and validation, focused tests for safe dry-run behavior, and a full SQLite-to-PostgreSQL runbook.

## Key Files

- `django-app/upload/management/__init__.py`
- `django-app/upload/management/commands/__init__.py`
- `django-app/upload/management/commands/prepare_postgres_migration.py`
- `django-app/upload/management/commands/validate_postgres_migration.py`
- `django-app/upload/tests.py`
- `documentation/sqlite-to-postgres-migration.md`

## Verification

- `python django-app\manage.py prepare_postgres_migration --dry-run` - passed.
- `python django-app\manage.py validate_postgres_migration --dry-run --include-audit` - passed.
- `python django-app\manage.py test upload` - passed.
- `python django-app\manage.py test lunit_audit upload` - passed.
- `python django-app\manage.py makemigrations --check --dry-run` - passed, no changes detected.
- Runbook keyword coverage for backup/export/import/validation/rollback/cutover/audit/synthetic/non-PHI - passed.

## Commits

| Commit | Description |
|--------|-------------|
| Pending | `feat(05-03): add sqlite to postgres migration tooling` |

## Deviations

- Validation command dry-run reports migration graph leaf nodes, not a live cross-database comparison, unless a distinct target alias is configured by the operator.
- Tests needed explicit database alias permission because the validation command inspects migration state.

## Self-Check

PASSED - Migration preparation and validation are dry-run safe by default, include both app and audit aliases, and the runbook covers backup, export/import, validation beyond row counts, rollback, and cutover.
