# 04-01 Summary: Multi-Stage Runtime Images

## Objective

Move Django and FastAPI images to multi-stage builds that keep build tools out of runtime stages.

## Completed

- Converted `django-app/Dockerfile` to a builder/runtime layout.
- Converted `cxr-audit-api/Dockerfile` to a builder/runtime layout.
- Kept `gcc` and `libffi-dev` in builder stages only.
- Copied installed Python packages from `/install` into runtime images.
- Preserved Django entrypoint behavior and FastAPI non-root execution.

## Verification

- Dockerfile structural check passed for both images:
  - builder stage present
  - runtime stage present
  - dependencies copied from builder
  - no runtime `apt-get install`
  - no runtime compiler package installation

## Notes

- Docker CLI was not available in this environment, so `docker compose config` and full image builds could not be executed locally.
