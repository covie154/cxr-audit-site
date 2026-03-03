# Security Fix #6: Add Content-Security-Policy Header

## Issue

The application had no Content-Security-Policy (CSP) header, leaving it more vulnerable to cross-site scripting (XSS) and data injection attacks. Without CSP, browsers allow any source of scripts, styles, and other resources, which increases the attack surface.

## Changes Made

### File: `nginx/nginx.conf`

Added a `Content-Security-Policy` header to the HTTPS server block, alongside the existing security headers:

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'self';
```

### Policy Breakdown

| Directive | Value | Reason |
|-----------|-------|--------|
| `default-src` | `'self'` | Only allow resources from the same origin by default |
| `script-src` | `'self' 'unsafe-inline'` | Allow self-hosted scripts and inline `<script>` blocks used throughout Django templates |
| `style-src` | `'self' 'unsafe-inline'` | Allow self-hosted stylesheets and inline `<style>` blocks (base.html uses inline CSS extensively) |
| `img-src` | `'self' data: blob:` | Allow self-hosted images, data URIs, and blob URLs (used for PDF preview/download) |
| `font-src` | `'self'` | Only system and self-hosted fonts are used |
| `connect-src` | `'self'` | All fetch/XHR calls target the same origin |
| `object-src` | `'none'` | No plugins (Flash, Java applets) are needed |
| `frame-ancestors` | `'self'` | Complements the existing X-Frame-Options SAMEORIGIN header |

## Template Audit

Before setting the policy, all Django templates were reviewed:

- **Inline scripts**: Found in `base.html`, `upload_interface.html`, `tasks.html`, `import_data.html`, `db_viewer.html`, `gt/index.html`, `report.html`. All use inline `<script>` blocks, requiring `'unsafe-inline'` in `script-src`.
- **Inline styles**: The `base.html` template embeds all CSS in a `<style>` block, and child templates extend it via `{% block extra_css %}`. This requires `'unsafe-inline'` in `style-src`.
- **External resources**: No CDN or third-party resources are loaded. All static files are served from Django's `{% static %}` path.
- **Fetch/XHR**: All API calls use relative URLs (same origin).
- **Blob URLs**: `report.js` uses `URL.createObjectURL()` and `window.open()` for PDF downloads, requiring `blob:` in `img-src`.

## Files Affected

- `nginx/nginx.conf`

## Reflections

- The use of `'unsafe-inline'` for scripts is not ideal from a security standpoint, as it reduces CSP's ability to prevent XSS. A future improvement would be to move inline scripts to external `.js` files and use nonce-based CSP (`script-src 'self' 'nonce-...'`). However, this would require changes to all Django templates and a middleware to generate and inject nonces.
- The `always` parameter ensures the header is sent even on error responses (e.g., 502, 503).
- The `frame-ancestors 'self'` directive in CSP is more flexible than `X-Frame-Options` and will eventually supersede it. Both are kept for browser compatibility.
- No `font-src` changes were needed since the application uses only system fonts (`'Segoe UI', system-ui, -apple-system, sans-serif`).
