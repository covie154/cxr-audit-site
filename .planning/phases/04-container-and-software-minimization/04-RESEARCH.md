# Phase 4 Research: Container And Software Minimization

Django and FastAPI final images currently install compiler/build packages directly. The least disruptive minimization path is multi-stage builds using `python:3.11-slim` for both builder and runtime stages, copying installed Python artifacts into the runtime stage.

Django currently needs root at entrypoint startup to chown named volumes, then uses `su` to run Django commands and Gunicorn as `appuser`. This should remain until a separate init-container or pre-provisioned volume ownership pattern exists.

Compose hardening should start with `no-new-privileges` and capability drops for Django/FastAPI. Read-only root filesystems are deferred because SQLite, static collection, media uploads, audit artifacts, and analysis temp files need careful write-path proof.
