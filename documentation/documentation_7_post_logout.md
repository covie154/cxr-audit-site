# Security Fix #7: Change Logout to POST-Only

## Issue

The logout endpoint at `/logout/` accepted GET requests (`http_method_names=["get", "post", "options"]`). Allowing GET-based logout is a security concern because:

1. **CSRF via link/image injection**: An attacker can embed `<img src="/logout/">` or a link on any page to force-logout a user without their consent.
2. **Browser prefetch**: Some browsers or extensions may prefetch links, causing unintended logouts.
3. **Log leakage**: GET requests appear in server access logs, browser history, and referer headers.

Django's own `LogoutView` documentation recommends POST-only logout since Django 5.0.

## Changes Made

### File: `django-app/lunit_audit/urls.py` (line 27)

Changed `http_method_names` from `["get", "post", "options"]` to `["post"]`.

No template changes were needed because the existing `base.html` template already uses a `<form method="post">` with a CSRF token for the logout button.

## Files Affected

- `django-app/lunit_audit/urls.py`

## Reflections

- The template was already correctly using a POST form for logout, so this change is purely on the server-side enforcement.
- Removing "options" is also fine since OPTIONS is primarily used for CORS preflight, and Django's CSRF middleware would block cross-origin POST requests anyway.
- This is a low-risk change since no existing functionality relies on GET logout (the template already uses POST).
