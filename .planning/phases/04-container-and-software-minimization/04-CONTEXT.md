# Phase 4: Container And Software Minimization - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Decision source:** `documentation/HIPAA-plan-phase-4.md`

<domain>
## Phase Boundary

This phase minimizes runtime container software and adds practical Compose hardening. It must preserve current writable paths and avoid changing clinical/data-processing dependencies.
</domain>

<decisions>
- **D-01:** Use multi-stage Dockerfiles to keep build tools out of runtime images.
- **D-02:** Keep `python:3.11-slim`.
- **D-03:** Django may start as root only for volume ownership, then drops to `appuser`.
- **D-04:** FastAPI runs as non-root `appuser`.
- **D-05:** Harden Nginx through Compose first, not a custom image.
- **D-06:** Add no-new-privileges and capability drops for Django/FastAPI.
- **D-07:** Document required writable paths.
- **D-08:** Do not enable read-only root filesystems in this phase.
- **D-09:** Keep FastAPI `/app/tmp` writable.
- **D-10:** Do not rewrite dependency pins.
- **D-11:** Verify with Compose/Django checks and Docker build where available.
- **D-12:** Document limits; do not claim full production container compliance.
</decisions>
