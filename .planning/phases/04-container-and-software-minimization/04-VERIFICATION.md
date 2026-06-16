# Phase 4 Verification: Container and Software Minimization

Date: 2026-06-14

## Commands Run

### Django Tests

Command:

```powershell
python django-app\manage.py test audit lunit_audit upload
```

Result: passed.

Notes:

- Initial run exposed an audit database schema issue: `AuditEvent.user` created a database-level foreign key to `auth_user`, but the audit database intentionally does not migrate the auth app.
- Fixed by setting `db_constraint=False` on `AuditEvent.user` and generating `audit.0003_alter_auditevent_user`.
- Final result: 8 tests passed.
- Expected warning remained: `lunit_audit.W002` for HTTP `LLM_BASE_URL` when `DEBUG=False`.

### FastAPI Tests

Command:

```powershell
python -m unittest discover -s cxr-audit-api\tests
```

Result: passed.

Notes:

- 7 tests passed.
- A deprecation warning from httpx test client usage was observed and is unrelated to Phase 4 container hardening.

### Migration Drift

Command:

```powershell
python django-app\manage.py makemigrations --check --dry-run
```

Result: passed.

Notes:

- `No changes detected`.
- Expected warning remained: `lunit_audit.W002`.

### Dockerfile Structural Check

Result: passed.

Assertions:

- `django-app/Dockerfile` and `cxr-audit-api/Dockerfile` both have builder/runtime stages.
- Runtime stages copy installed packages from `/install` into `/usr/local`.
- Runtime stages do not run `apt-get install`.
- Runtime stages do not install compiler packages.

### Compose Structural Check

Result: passed.

Assertions:

- Django has `no-new-privileges:true`.
- Django capability drops are deferred.
- FastAPI has `no-new-privileges:true`.
- FastAPI has `cap_drop: ["ALL"]`.
- `django-staticfiles` and `django-audit-artifacts` named volumes exist.
- Django mounts `/app/staticfiles` and `/app/audit_artifacts`.

## Not Run

`docker compose config` and full image builds were not run because Docker is not available in this environment.

## Follow-Up Items

- Replace Django startup root `chown` with external volume provisioning or an init-container pattern, then revisit `cap_drop: ["ALL"]` for Django.
- Test full Docker builds in an environment with Docker and package-index access.
- Consider read-only root filesystems after every required write path is mapped and exercised in Docker.
