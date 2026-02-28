# Security Fix #3: Docker Container Runs as Non-Root

## Issue

The CXR Audit API Docker container was running as the default `root` user. This is a security risk because if an attacker gains code execution inside the container, they have full root privileges, which can facilitate container escape or lateral movement.

## Changes Made

### File: `cxr-audit-api/Dockerfile`

1. **Added a non-root user**: Added `RUN adduser --disabled-password --no-create-home appuser` to create a dedicated unprivileged user.
2. **Switched to non-root user**: Added `USER appuser` directive before the `HEALTHCHECK` and `CMD` instructions, ensuring the application process runs as `appuser` instead of `root`.

### File: `django-app/Dockerfile`

1. **Added a non-root user**: Added `RUN adduser --disabled-password --no-create-home appuser` to create a dedicated unprivileged user.
2. **Set ownership of writable directories**: Used `chown -R appuser:appuser` on `/app/db`, `/app/media`, and `/app/staticfiles` since these are volume-mounted directories that Django needs write access to.
3. **Switched to non-root user**: Added `USER appuser` directive before the `ENTRYPOINT` instruction.

In both Dockerfiles the `USER` directive is placed after all `RUN`, `COPY`, and permission-related commands (which require root) but before the runtime instructions.

## Why This Fix

Running containers as non-root is a widely recommended security best practice (CIS Docker Benchmark, OWASP). It follows the principle of least privilege -- the API application does not need root access to serve HTTP responses. The application code only reads JSON configs and Python files (owned by root but world-readable by default), and writes to `/tmp` via Python's `tempfile` module (which uses the system temp directory, writable by all users).

## Files Affected

- `cxr-audit-api/Dockerfile`
- `django-app/Dockerfile`

## Reflections

- The `--no-create-home` flag keeps the image lean by not creating an unnecessary home directory.
- Python's `tempfile` module uses `/tmp` by default, which has `1777` permissions on Debian-based images, so no ownership change is needed for the API container.
- The Django container needed explicit `chown` for its volume-mounted directories (`db`, `media`, `staticfiles`) because Docker named volumes are initialized as root-owned. Without this, Django would fail to write to the SQLite database or save uploaded media files.
- The nginx container already runs as non-root by default (nginx alpine uses `nginx` user internally), so no change was needed there.
