# Security Fix #2: Add API Key Authentication

## Summary
The FastAPI backend had no authentication, allowing any network client that could reach port 1221 to invoke analysis endpoints. This change adds API key authentication via an `X-API-Key` header, shared between the Django frontend and the FastAPI backend.

## Changes Made

### Files Modified

1. **cxr-audit-api/combined_server.py**
   - Added `APIKeyHeader` security scheme and `verify_api_key` dependency
   - Registered the dependency globally on `api_app` so all API endpoints are protected
   - When `API_SECRET_KEY` env var is empty/unset, authentication is skipped (development mode)
   - Returns HTTP 403 when the key is missing or incorrect

2. **django-app/upload/views.py**
   - Added `import os`
   - Added `get_api_headers()` helper that returns `{"X-API-Key": ...}` when the env var is set
   - Added `headers=get_api_headers()` to all 7 `requests.get/post` calls that communicate with the FastAPI backend (lines for status polling, results fetching, file uploads, and health checks)

3. **.env.example**
   - Added `API_SECRET_KEY=change-me-to-a-random-secret` with generation instructions

## Environment Variable
- **Name**: `API_SECRET_KEY`
- **Required**: Yes, for production. When empty, authentication is disabled (for local development).
- **Shared by**: Both `django` and `api` services via the common `.env` file in `docker-compose.yml`

## Deployment Note
After deploying, generate a strong random key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Set it in `.env` as `API_SECRET_KEY=<generated-value>`.

## Reflections
- Using a global FastAPI dependency (`dependencies=[Depends(verify_api_key)]`) ensures that any new endpoints added in the future are automatically protected.
- The development fallback (empty key = no auth) makes local testing convenient but should be documented as a conscious trade-off.
- A future improvement would be to use short-lived tokens (JWT) instead of a static shared secret, but for an internal service-to-service call behind a Docker network, a shared API key is a reasonable first step.
