# Phase 3: Network Segmentation - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Decision source:** `documentation/HIPAA-plan-phase-3.md`

<domain>
## Phase Boundary

This phase changes Docker Compose network topology only. It creates explicit public, app, data, and inference network boundaries while preserving current service names and upload-to-analysis routing.
</domain>

<decisions>
- **D-01:** Define `primer-public`, `primer-app`, `primer-data`, and `primer-inference`.
- **D-02:** Nginx joins only public and app networks.
- **D-03:** Django joins app and data networks.
- **D-04:** FastAPI joins app and inference networks.
- **D-05:** Only Nginx host ports are exposed by default.
- **D-06:** Mark app/data internal, leave inference non-internal.
- **D-07:** Do not add PostgreSQL until Phase 5.
- **D-08:** Preserve `django` and `api` DNS names.
- **D-09:** Verify with Compose config and healthcheck shape.
- **D-10:** Future DB services should join only data network.
- **D-11:** Certs stay mounted only on Nginx.
- **D-12:** Do not expose the legacy FastAPI static UI.
</decisions>
