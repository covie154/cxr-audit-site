# Issue #9: Extract Inline CSS/JS to External Files

## Summary

Extracted all inline `<style>` blocks, `<script>` blocks, and inline event handlers
(`onclick`, `onchange`) from Django templates into external static files. This enables
a future move from `'unsafe-inline'` to nonce-based CSP headers, dramatically improving
XSS protection.

## Changes

### New Static Files Created (15 files)

**CSS files (8):**
| File | Source Template |
|------|---------------|
| `static/css/base.css` | `base.html` |
| `static/css/login.css` | `registration/login.html` |
| `upload/static/upload/upload.css` | `upload/upload_interface.html` |
| `upload/static/upload/tasks.css` | `upload/tasks.html` |
| `upload/static/upload/import.css` | `upload/import_data.html` |
| `viewer/static/viewer/viewer.css` | `viewer/db_viewer.html` |
| `gt/static/gt/gt.css` | `gt/index.html` |
| `report/static/report/report.css` | *(already existed)* |

**JS files (7):**
| File | Source Template |
|------|---------------|
| `static/js/base.js` | `base.html` (hamburger menu) |
| `upload/static/upload/upload.js` | `upload/upload_interface.html` |
| `upload/static/upload/tasks.js` | `upload/tasks.html` |
| `upload/static/upload/import.js` | `upload/import_data.html` |
| `viewer/static/viewer/viewer.js` | `viewer/db_viewer.html` |
| `gt/static/gt/gt.js` | `gt/index.html` |
| `report/static/report/report.js` | *(already existed, updated)* |

### Templates Modified (9 files)

1. **`base.html`** — Replaced inline `<style>` with `<link>` to `base.css`, inline `<script>` with `<script src>` to `base.js`. Removed `{% block extra_css %}` (was inside `<style>` tag). Child templates now use `{% block extra_head %}` for CSS links.

2. **`registration/login.html`** — Replaced `{% block extra_css %}` with `{% block extra_head %}` containing `<link>` to `login.css`.

3. **`upload/upload_interface.html`** — Extracted CSS and JS. Replaced inline `onclick` on file-drop zones and precheck buttons with `addEventListener` in `upload.js`. Added `window.PAGE_CONFIG` for Django template variables.

4. **`upload/tasks.html`** — Extracted CSS and JS. Replaced `onclick="confirmDelete('{{ task_id }}')"` with `data-task-id` attributes and event delegation. Modal buttons use `addEventListener`.

5. **`upload/import_data.html`** — Extracted CSS and JS. Replaced `onclick="clearFile()"` and `onclick="doImport()"` with `addEventListener`. Added `window.PAGE_CONFIG`.

6. **`viewer/db_viewer.html`** — Extracted CSS and JS. Replaced 11 inline handlers:
   - `onchange="this.form.submit()"` → `addEventListener('change')`
   - `onclick="setSort(...)"` → `data-sort` attribute + delegated listener
   - `onclick="toggleSelectAll(this)"` → `addEventListener`
   - `onclick="updateSelection()"` → delegated via `.table-wrap` click handler
   - `onclick="openDetail(...)"` / `onclick="deleteStudy(...)"` → `data-action` + `data-accession` attributes + event delegation
   - Modal buttons → `data-action="close-modal"` + `addEventListener`
   - Added `window.PAGE_CONFIG` for `csrfToken` and `allFilteredIds`.

7. **`gt/index.html`** — Extracted CSS and JS. No inline handlers existed (already used `addEventListener`).

8. **`report/report.html`** — Removed `onclick` from 6 buttons (`generateReport`, `downloadCSV`, `downloadPDF`, `openEmailModal`, `closeEmailModal`, `sendEmailReport`). Added IDs where needed.

9. **`report/report.js`** — Added `addEventListener` calls for all report page buttons. Changed dynamically-created FN/FP CSV download buttons from inline `onclick` to `addEventListener`.

### Django Template Variable Pattern

Templates that use Django-injected values define a minimal inline `<script>` block:

```html
<script>
    window.PAGE_CONFIG = {
        csrfToken: '{{ csrf_token }}',
        apiBaseUrl: '{% url "upload:index" %}'.replace(/\/$/, '') + '/api',
    };
</script>
<script src="{% static 'upload/upload.js' %}"></script>
```

External JS files read from `window.PAGE_CONFIG` instead of Django template tags.

### Templates NOT Modified

- **`report/print_report.html`** — Standalone PDF rendering page, not served via CSP-enabled nginx
- **`report/email_report.html`** — Email HTML requiring inline styles for email client compatibility

## Verification Checklist

- [x] No `<style>` blocks in templates (except `print_report.html`)
- [x] No `{% block extra_css %}` blocks remain
- [x] No inline `onclick`/`onchange` in Django app templates
- [x] Only minimal `<script>` blocks remain (for `window.PAGE_CONFIG`)
- [x] All static files follow Django app convention (`app/static/app/file.ext`)
- [x] Base static files in project-level `static/` directory
