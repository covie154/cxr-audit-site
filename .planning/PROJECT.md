# PRIMER-LLM HIPAA Compliance

## What This Is

PRIMER-LLM is a Django and FastAPI medical imaging audit application that processes CARPL CSVs and RIS exports containing chest X-ray report ePHI, grades reports through an OpenAI-compatible LLM endpoint, and stores study-level audit and reporting results. This project cycle hardens the existing `django/` deployment toward HIPAA technical safeguard compliance while preserving the current upload, viewer, report, manual GT, and LLM grading workflows.

## Core Value

PRIMER-LLM must protect ePHI access, transmission, storage, and auditability without breaking the chest X-ray audit workflow clinicians and auditors already use.

## Requirements

### Validated

- [x] Users can upload CARPL/Lunit CSV files and GE/RIS Excel exports for analysis through the Django upload UI.
- [x] Django can proxy analysis jobs to the FastAPI backend and persist completed results into `CXRStudy`.
- [x] Users can view generated report metrics, CSV exports, false-negative/false-positive lists, and time analysis.
- [x] Admin users can browse, search, filter, export, edit, and delete study records through the viewer app.
- [x] Users can download stratified manual GT samples and upload labels back into the database.
- [x] The analysis backend can call an OpenAI-compatible LLM endpoint for report grading and supplemental findings extraction.
- [x] The Docker deployment runs Nginx, Django/Gunicorn, and FastAPI behind HTTPS-capable Nginx.

### Active

- [ ] Add structured, tamper-evident audit logging for ePHI access across Django views, FastAPI task endpoints, database mutations, exports, authentication events, administrative actions, and LLM prompt/response interactions.
- [ ] Harden transmission security for external and internal traffic, including Django secure-cookie/security settings, Nginx TLS/HSTS posture, service-to-service authentication, and documented expectations for the OpenAI-compatible LLM endpoint transport.
- [ ] Segment the Docker network into explicit public, application, data, and inference boundaries so only intended services can reach each other.
- [ ] Remove extraneous production software and harden containers by minimizing image contents, dropping capabilities, using non-root execution, avoiding writable root filesystems where possible, and documenting required writable mounts.
- [ ] Add PostgreSQL support as a production database option while preserving SQLite for local development when appropriate.
- [ ] Produce a SQLite-to-PostgreSQL migration plan covering schema migration, data export/import, validation, rollback, backups, encrypted storage expectations, and operational cutover.
- [ ] Create a follow-on HIPAA implementation ordering document for the remaining controls after the first five feature areas.

### Out of Scope

- Administrative HIPAA compliance artifacts such as workforce training, policy signoff, formal risk analysis ownership, sanctions policy, and business associate agreements - required for full compliance but not implemented as application code in this cycle.
- Physical safeguards and host facility controls - outside the Django repository boundary.
- Replacing the existing LLM grading methodology or clinical scoring logic - this cycle hardens the system around the existing workflow.
- Migrating historical research/data folders outside `django/` - only the Django Git repository is in scope.
- Using a cloud LLM provider for PHI without a BAA - the app should target a controlled OpenAI-compatible endpoint such as vLLM.

## Context

The source of compliance intent is `../Docs & Posters/HIPAA.md`. It frames the target as HIPAA technical safeguards for a Django web UI, FastAPI analysis API, Nginx, Docker Compose, and an OpenAI-compatible LLM endpoint processing chest X-ray report ePHI.

The existing codebase map is in `.planning/codebase/`. It identifies the core request flow as browser to Nginx, Nginx to Django, Django to FastAPI, FastAPI to an OpenAI-compatible LLM endpoint, then Django persistence into `CXRStudy`.

Current HIPAA-relevant gaps include no structured audit logging, SQLite as the production-style database, plain HTTP on internal service hops, a single Docker bridge network, optional FastAPI API-key enforcement when `API_SECRET_KEY` is empty, state-changing Django endpoints with `@csrf_exempt`, process-local task state, limited executable tests, and container hardening gaps.

The requested implementation order is deliberate:

1. Audit logging.
2. Transmission security.
3. Network segmentation.
4. Removal of extraneous software.
5. PostgreSQL support and migration planning.
6. Planning document for the remaining HIPAA controls.

## Constraints

- **Repository boundary**: Only `django/` is a Git repository; planning artifacts and commits must live under `django/.planning/` and `django/.git`.
- **Production data sensitivity**: `CXRStudy`, uploaded files, FastAPI task payloads, generated CSVs, email reports, LLM prompts, and LLM responses may contain ePHI.
- **LLM backend**: Treat the inference service as an OpenAI-compatible endpoint, currently vLLM-compatible; do not assume Ollama-specific runtime behavior even if legacy env var names still contain `OLLAMA_*`.
- **Deployment model**: Docker Compose and Nginx are the current deployment base and should be hardened incrementally rather than replaced wholesale.
- **Database compatibility**: PostgreSQL support must not casually break local development workflows that still use SQLite.
- **Testing**: HIPAA security work must add focused regression coverage for changed controls because the current Django deployment has little executable test coverage.
- **Data access**: Avoid reading or committing PHI-bearing datasets from outside `django/` unless explicitly required.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Scope GSD planning to `django/` only | `django/` is the actual Git repository; the PRIME root is a broader research workspace | Pending |
| Use the codebase map as brownfield context before planning HIPAA work | Existing architecture and security gaps should drive requirements and roadmap | Pending |
| Generalize the LLM tier as OpenAI-compatible rather than Ollama-specific | The backend has changed to vLLM-compatible deployment while code still uses legacy env var names | Pending |
| Implement audit logging first | Audit controls are central to HIPAA technical safeguards and cross-cut all ePHI workflows | Pending |
| Add PostgreSQL as a production option after initial security hardening | Database migration should be planned after audit, transport, network, and container boundaries are clearer | Pending |
| Target technical controls for internal review | This milestone should produce demonstrable technical controls and documented gaps, not claim complete production HIPAA compliance | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason.
2. Requirements validated? -> Move to Validated with phase reference.
3. New requirements emerged? -> Add to Active.
4. Decisions to log? -> Add to Key Decisions.
5. "What This Is" still accurate? -> Update if drifted.

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections.
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state.

---
*Last updated: 2026-06-14 after initialization*
