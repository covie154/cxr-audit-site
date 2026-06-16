# 04-03 Summary: Writable Runtime Paths

## Objective

Document writable paths and preserve required runtime write locations.

## Completed

- Added named Compose volumes for Django static files and audit artifacts.
- Mounted `django-staticfiles` at `/app/staticfiles`.
- Mounted `django-audit-artifacts` at `/app/audit_artifacts`.
- Updated `django-app/entrypoint.sh` so startup ownership repair includes `/app/audit_artifacts`.
- Kept read-only root filesystem hardening deferred until runtime write paths can be proven in a running Docker environment.
- Updated `documentation/HIPAA-plan-phase-4.md` with the writable-path and read-only-root rationale.

## Verification

- Compose YAML structural check passed:
  - `django-staticfiles` named volume exists.
  - `django-audit-artifacts` named volume exists.
  - Django mounts `/app/staticfiles`.
  - Django mounts `/app/audit_artifacts`.

## Notes

- FastAPI still requires `/app/tmp` as a writable runtime path for analysis temp files and Matplotlib cache behavior.
