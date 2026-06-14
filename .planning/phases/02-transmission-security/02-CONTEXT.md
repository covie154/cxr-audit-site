# Phase 2: Transmission Security - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Decision source:** `documentation/HIPAA-plan-phase-2.md`

<domain>
## Phase Boundary

This phase hardens production transport posture and Django-to-FastAPI service authentication. It covers Django/Nginx secure settings, FastAPI fail-closed API-key behavior, Django header forwarding, CORS tightening, and practical OpenAI-compatible endpoint transport validation/documentation.

This phase does not implement internal mTLS, network segmentation, PostgreSQL, MFA/RBAC, or broad CSRF cleanup.
</domain>

<decisions>
## Implementation Decisions

- **D-01:** FastAPI requires `X-API-Key` when `DJANGO_DEBUG=False` or `API_REQUIRE_AUTH=True`.
- **D-02:** Missing required production API secret returns `503`.
- **D-03:** Add unauthenticated `/health` for container health only.
- **D-04:** Django continues sourcing `API_SECRET_KEY` from environment and sends `X-API-Key`.
- **D-05:** Django production security settings include SSL redirect, HSTS, secure cookies, proxy SSL header, and related headers.
- **D-06:** Nginx remains edge HTTPS redirector; Django redirects only when `DEBUG=False`.
- **D-07:** FastAPI CORS origins are environment-driven and restrictive in production.
- **D-08:** Add practical production LLM transport validation/warnings.
- **D-09:** Document mTLS as later hardening.
- **D-10:** Add focused synthetic tests.
- **D-11:** Do not write real secrets into docs or tests.
- **D-12:** Preserve permissive local development only when explicitly debug/non-production.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` - SEC-01 through SEC-05.
- `.planning/ROADMAP.md` - Phase 2 success criteria and plan split.
- `documentation/HIPAA-plan-phase-2.md` - accepted decisions and alternatives.
- `django-app/lunit_audit/settings.py` - Django security, API, and LLM settings.
- `django-app/upload/views.py` - Django-to-FastAPI request headers and health checks.
- `cxr-audit-api/combined_server.py` - FastAPI auth, CORS, and health endpoints.
- `nginx/nginx.conf` - edge TLS and security headers.
- `docker-compose.yml` - health checks and service env.
- `.env.example` - production-style configuration contract.
</canonical_refs>

<deferred>
## Deferred Ideas

- Internal mTLS and certificate lifecycle.
- Full CSRF decorator cleanup.
- Production evidence report.
</deferred>
