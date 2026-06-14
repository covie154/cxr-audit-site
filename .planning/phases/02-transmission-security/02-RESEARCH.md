# Phase 2 Research: Transmission Security

**Phase:** 02-transmission-security
**Researched:** 2026-06-14
**Status:** Ready for planning

## Technical Approach

The project already has partial controls: Nginx redirects HTTP to HTTPS, Django sets secure cookies when `DEBUG=False`, and Django sends `X-API-Key` to FastAPI if `API_SECRET_KEY` is configured. The main gap is permissive failure behavior: FastAPI allows anonymous calls when the secret is empty, and wildcard CORS remains enabled.

The safest brownfield approach is to make production fail closed while keeping local development usable:

- Use `DJANGO_DEBUG=False` and/or `API_REQUIRE_AUTH=True` to require FastAPI service auth.
- Preserve unauthenticated `/health` for Docker health checks.
- Add Django system checks for production transport risks rather than hard-failing local dev.
- Keep Nginx as the browser TLS edge.

## Risks And Mitigations

- **Breaking Docker health checks:** add `/health` and point health checks there.
- **Breaking local dev:** fail closed only when production-style flags are active.
- **False confidence around HTTP LLM endpoint:** document and warn unless HTTP private transport is explicitly allowed.
- **Secret leakage:** tests and docs use placeholders only.

## Verification Focus

- `python django-app/manage.py check`
- `python django-app/manage.py test audit upload lunit_audit`
- FastAPI auth unit tests with synthetic requests.
- `docker compose config`
