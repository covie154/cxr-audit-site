# PRIMER-LLM Visual Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved PRIMER clinical design system and responsive navigation shell across every existing Django screen without changing visible copy, workflow behavior, permissions, or dashboard structure.

**Architecture:** Convert the shared base template and stylesheet into a token-driven application shell, then migrate each page stylesheet in place while preserving all existing template and JavaScript contracts. Keep the vanilla Django/HTML/CSS/JavaScript architecture, self-host the brand/font assets, and verify both template contracts and representative browser behavior.

**Tech Stack:** Django 5 templates, vanilla JavaScript, CSS custom properties, Django staticfiles, Django `SimpleTestCase`

**Spec:** `docs/superpowers/specs/2026-08-22-primer-visual-migration-design.md`

## Global Constraints

- Do not change headings, labels, instructions, button text, status text, or other visible copy.
- Do not change workflows, URLs, views, models, form submissions, filtering, exports, uploads, tasks, reports, manual-GT behavior, roles, or permissions.
- Do not add React, a frontend framework, a runtime CDN, or third-party font requests.
- Preserve all `window.PAGE_CONFIG` values and JavaScript-referenced IDs, classes, and data attributes.
- Preserve the Report page's current structure and content.
- Keep role-dependent navigation visibility exactly as implemented today.
- Do not inspect clinical data; use empty or synthetic test state only.

---

### Task 1: Shared Clinical Shell and Design Tokens

**Files:**
- Create: `django-app/static/img/primer-mark.svg`
- Create: `django-app/static/fonts/space-grotesk-latin.woff2`
- Create: `django-app/static/fonts/ibm-plex-sans-regular-latin.woff2`
- Create: `django-app/static/fonts/ibm-plex-sans-medium-latin.woff2`
- Create: `django-app/static/fonts/ibm-plex-sans-semibold-latin.woff2`
- Create: `django-app/static/fonts/ibm-plex-mono-medium-latin.woff2`
- Create: `django-app/static/fonts/OFL-Space-Grotesk.txt`
- Create: `django-app/static/fonts/OFL-IBM-Plex.txt`
- Modify: `django-app/lunit_audit/tests.py`
- Modify: `django-app/templates/base.html`
- Modify: `django-app/static/css/base.css`
- Modify: `django-app/static/js/base.js`

**Interfaces:**
- Consumes: existing `{% block title %}`, `extra_head`, `nav_*`, `header_right`, `body`, and `extra_js` blocks; `user` and `is_admin` template context.
- Produces: `.app-shell`, `#primaryNavigation`, `#menuToggle`, `#navBackdrop`, `#mainContent`, `.app-sidebar`, `.app-topbar`, shared CSS tokens, and drawer behavior used by every page.

- [ ] **Step 1: Add failing shared-shell template tests**

Append tests that render a child template against `base.html` without touching the database:

```python
from django.contrib.auth.models import AnonymousUser, User
from django.template import engines
from django.test import SimpleTestCase


class VisualShellTemplateTests(SimpleTestCase):
    def _render_shell(self, user, is_admin=False):
        template = engines["django"].from_string(
            "{% extends 'base.html' %}{% block nav_report %}active{% endblock %}"
            "{% block body %}<p>Shell probe</p>{% endblock %}"
        )
        return template.render({"user": user, "is_admin": is_admin})

    def test_authenticated_shell_has_sidebar_landmarks_and_active_page(self):
        html = self._render_shell(User(username="reviewer"))
        self.assertIn('id="primaryNavigation"', html)
        self.assertIn('id="mainContent"', html)
        self.assertIn('aria-current="page"', html)
        self.assertIn("Shell probe", html)

    def test_admin_shell_retains_admin_only_destinations(self):
        html = self._render_shell(User(username="admin", is_superuser=True), is_admin=True)
        for label in ("Tasks", "Import", "Database"):
            self.assertIn(label, html)

    def test_unauthenticated_shell_omits_application_navigation(self):
        html = self._render_shell(AnonymousUser())
        self.assertNotIn('id="primaryNavigation"', html)
        self.assertIn('id="mainContent"', html)
```

- [ ] **Step 2: Run the shell tests and verify they fail**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualShellTemplateTests -v 2`

Expected: FAIL because the current template has neither `primaryNavigation`, `mainContent`, nor `aria-current`.

- [ ] **Step 3: Add the approved static assets**

Copy the supplied SVG paths into `django-app/static/img/primer-mark.svg`. Download the Latin WOFF2 subsets for Space Grotesk and IBM Plex from their official upstream repositories, add the corresponding OFL license texts, and verify no CSS references an external URL.

Run: `rg -n "https?://|@import" django-app/static/css django-app/static/fonts`

Expected: no font CDN or stylesheet import.

- [ ] **Step 4: Implement the shared application shell**

Update `base.html` to retain every existing Django block while adding:

```html
<a class="skip-link" href="#mainContent">Skip to content</a>
<div class="app-shell{% if not user.is_authenticated %} app-shell--guest{% endif %}">
  {% if user.is_authenticated %}
  <aside class="app-sidebar" id="primaryNavigation" aria-label="Primary navigation">
    <!-- existing destinations, labels, permission conditions, username, and logout form -->
  </aside>
  <button class="nav-backdrop" id="navBackdrop" type="button" aria-label="Close navigation"></button>
  {% endif %}
  <div class="app-workspace">
    {% if user.is_authenticated %}<header class="app-topbar"><!-- existing controls --></header>{% endif %}
    <main id="mainContent" class="app-main" tabindex="-1">{% block body %}{% endblock %}</main>
  </div>
</div>
```

For each navigation link, render `aria-current="page"` only when its existing `nav_*` block resolves to `active`. Preserve `header_right` in the authenticated shell.

- [ ] **Step 5: Replace shared CSS with production tokens and primitives**

Define local `@font-face` rules and the approved token map:

```css
:root {
  --nav-w: 236px;
  --c-bg: #f4f6f9;
  --c-surface: #ffffff;
  --c-surface-muted: #edf1f6;
  --c-text: #111a2b;
  --c-text-muted: #5a6478;
  --c-border: #dce3ec;
  --c-primary: #0e7c86;
  --c-primary-dark: #0a5a62;
  --c-success: #2f855a;
  --c-warning: #c05621;
  --c-danger: #c5303b;
  --c-focus: #2563c9;
  --font-display: "Space Grotesk", sans-serif;
  --font-sans: "IBM Plex Sans", sans-serif;
  --font-mono: "IBM Plex Mono", monospace;
  --radius: 10px;
}
```

Implement the desktop sidebar, compact top bar, main content canvas, shared component states, `:focus-visible`, mobile drawer, print safety, and `prefers-reduced-motion`. Retain compatibility variables used by page CSS/JavaScript.

- [ ] **Step 6: Implement accessible drawer behavior**

Replace the old collapse toggle in `base.js` with functions that maintain `aria-expanded`, the `.is-open` class, body scroll locking, Escape handling, backdrop close, link close below the mobile breakpoint, and focus return to `#menuToggle`.

- [ ] **Step 7: Run focused tests and static checks**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualShellTemplateTests -v 2`

Expected: PASS.

Run: `cd django-app && python manage.py findstatic img/primer-mark.svg css/base.css js/base.js --verbosity 2`

Expected: all assets resolve from `django-app/static/`.

- [ ] **Step 8: Commit the shared shell**

```bash
git add django-app/lunit_audit/tests.py django-app/templates/base.html django-app/static/css/base.css django-app/static/js/base.js django-app/static/img django-app/static/fonts
git commit -m "feat: add PRIMER clinical application shell"
```

---

### Task 2: Login and Upload Workflow Styling

**Files:**
- Modify: `django-app/static/css/login.css`
- Modify: `django-app/upload/templates/upload/upload_interface.html`
- Modify: `django-app/upload/templates/upload/tasks.html`
- Modify: `django-app/upload/templates/upload/import_data.html`
- Modify: `django-app/upload/static/upload/upload.css`
- Modify: `django-app/upload/static/upload/tasks.css`
- Modify: `django-app/upload/static/upload/import.css`
- Test: `django-app/lunit_audit/tests.py`

**Interfaces:**
- Consumes: Task 1 tokens and shared card/button/form styles.
- Produces: styled guest login, upload, task, and import layouts while retaining all current page IDs and `window.PAGE_CONFIG` contracts.

- [ ] **Step 1: Add failing copy-and-selector preservation tests**

Add a source-contract test that reads the three upload templates and asserts the JavaScript-critical IDs and representative existing copy remain present:

```python
from pathlib import Path


class VisualMigrationSourceContractTests(SimpleTestCase):
    templates_root = Path(__file__).resolve().parents[1]

    def test_upload_templates_keep_interaction_contracts(self):
        cases = {
            "upload/templates/upload/upload_interface.html": (
                "Upload &amp; Analyze", 'id="uploadForm"', 'id="lunitFiles"',
                'id="gtFiles"', 'id="precheckPanel"', 'id="statusContainer"',
            ),
            "upload/templates/upload/tasks.html": (
                "Processing Tasks", 'id="backfillForm"', 'id="deleteModal"',
                'id="confirmDeleteBtn"',
            ),
            "upload/templates/upload/import_data.html": (
                "Import Historical Data", 'id="uploadZone"', 'id="previewCard"',
                'id="btnImport"', 'id="resultCard"',
            ),
        }
        for relative, required in cases.items():
            source = (self.templates_root / relative).read_text(encoding="utf-8")
            for marker in required:
                self.assertIn(marker, source, f"{marker} missing from {relative}")
```

- [ ] **Step 2: Run the source-contract test**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests.test_upload_templates_keep_interaction_contracts -v 2`

Expected: PASS before styling; this establishes the behavior/copy guardrail.

- [ ] **Step 3: Restyle the login page**

Use the existing login markup and copy. Implement a centered branded card on the slate canvas, display typography for the product title, high-contrast fields, teal sign-in action, prototype radii, and responsive spacing. Do not add, remove, or rewrite form fields or messages.

- [ ] **Step 4: Restyle Upload and Analyze**

Keep the existing form structure and IDs. Convert file drops, supplemental toggle, status panels, progress, metrics, and result actions to shared tokens. Use semantic colors only for connection/status meaning and ensure focus states remain visible.

- [ ] **Step 5: Restyle Processing Tasks**

Preserve the existing table, backfill form, badges, progress indicators, modal, and inline copy. Apply display headings, mono dates/numbers, muted table headers, semantic status pills, teal progress/action states, and responsive horizontal scrolling.

- [ ] **Step 6: Restyle Import Historical Data**

Preserve the drop zone, mode selection, preview, mapping table, loading state, results, and all IDs. Apply tokenized surfaces, mono metrics/mappings, semantic preview tiles, and mobile-safe action wrapping.

- [ ] **Step 7: Run upload-family regression checks**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests upload -v 2`

Expected: PASS.

Run: `rg -n "#3b82f6|#2563eb|#eff6ff|#dbeafe" django-app/static/css/login.css django-app/upload/static/upload`

Expected: no legacy action-blue palette remains except a documented semantic focus color.

- [ ] **Step 8: Commit the login and upload-family migration**

```bash
git add django-app/lunit_audit/tests.py django-app/static/css/login.css django-app/upload/templates django-app/upload/static/upload
git commit -m "feat: restyle PRIMER upload workflows"
```

---

### Task 3: Database Viewer Styling

**Files:**
- Modify: `django-app/viewer/templates/viewer/db_viewer.html`
- Modify: `django-app/viewer/static/viewer/viewer.css`
- Test: `django-app/lunit_audit/tests.py`

**Interfaces:**
- Consumes: Task 1 shell, tokens, shared controls, cards, tables, badges, modals, and toasts.
- Produces: dense clinical database viewer preserving every `viewer.js` selector and server-rendered filter/control.

- [ ] **Step 1: Extend the source-contract test for the viewer**

```python
def test_viewer_template_keeps_interaction_contracts(self):
    source = (self.templates_root / "viewer/templates/viewer/db_viewer.html").read_text(encoding="utf-8")
    for marker in (
        'id="filterForm"', 'class="table-wrap"', 'id="selectAll"',
        'id="selectAllFilteredBtn"', 'id="bulkDeleteBtn"',
        'id="detailModal"', 'id="modalBody"', 'id="saveDetailBtn"',
        'id="toast"',
    ):
        self.assertIn(marker, source)
```

- [ ] **Step 2: Run the viewer contract test**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests.test_viewer_template_keeps_interaction_contracts -v 2`

Expected: PASS before styling.

- [ ] **Step 3: Apply the clinical data-grid presentation**

Preserve filter order, table columns, pagination, modal fields, and action controls. Style the toolbar as a wrapped surface, use sticky muted headers and mono identifiers/numbers, retain horizontal table scrolling, highlight selection without semantic red/green misuse, and use the prototype's density and border treatment.

- [ ] **Step 4: Restyle viewer modal, pagination, selection, and toast states**

Use shared modal and focus behavior, tokenized read-only fields, teal current-page and primary actions, and red only for destructive controls. Preserve `.open`, `.selected`, and all event-selector classes.

- [ ] **Step 5: Run viewer regression checks**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests viewer -v 2`

Expected: PASS.

Run: `rg -n "#3b82f6|#2563eb|#eff6ff|#dbeafe" django-app/viewer/static/viewer`

Expected: no legacy action-blue palette remains except a documented semantic focus color.

- [ ] **Step 6: Commit the viewer migration**

```bash
git add django-app/lunit_audit/tests.py django-app/viewer/templates/viewer/db_viewer.html django-app/viewer/static/viewer/viewer.css
git commit -m "feat: restyle PRIMER database viewer"
```

---

### Task 4: Report and Manual Ground Truth Styling

**Files:**
- Modify: `django-app/report/templates/report/report.html`
- Modify: `django-app/report/static/report/report.css`
- Modify: `django-app/gt/templates/gt/index.html`
- Modify: `django-app/gt/static/gt/gt.css`
- Test: `django-app/lunit_audit/tests.py`

**Interfaces:**
- Consumes: Task 1 tokens and shared data/card/form primitives.
- Produces: visually migrated Report and Manual GT workflows with existing content, dashboard structure, chart canvases, and JavaScript selectors unchanged.

- [ ] **Step 1: Extend source-contract tests for Report and Manual GT**

```python
def test_report_and_gt_templates_keep_interaction_contracts(self):
    cases = {
        "report/templates/report/report.html": (
            'id="generateBtn"', 'id="resultsSection"', 'id="summaryCards"',
            'id="siteTableBody"', 'id="fnSection"', 'id="fpSection"',
            'id="emailModal"', 'id="sendEmailBtn"',
        ),
        "gt/templates/gt/index.html": (
            'id="startDate"', 'id="endDate"', 'id="downloadBtn"',
            'id="gtFileDrop"', 'id="gtFileInput"', 'id="validateBtn"',
            'id="mappingSection"', 'id="uploadBtn"', 'id="resultPanel"',
        ),
    }
    for relative, required in cases.items():
        source = (self.templates_root / relative).read_text(encoding="utf-8")
        for marker in required:
            self.assertIn(marker, source, f"{marker} missing from {relative}")
```

- [ ] **Step 2: Run the Report/GT contract test**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests.test_report_and_gt_templates_keep_interaction_contracts -v 2`

Expected: PASS before styling.

- [ ] **Step 3: Restyle Report without restructuring it**

Keep every current section, heading, input, button, chart canvas, generated-results target, comparison table, false-negative/false-positive section, download action, and email modal. Apply prototype typography and surfaces, mono metric values, teal actions, semantic result colors, compact table headers, and responsive wrapping. Do not change `report.js` or `charts.js` unless a browser check proves shell integration requires it.

- [ ] **Step 4: Restyle Manual Ground Truth**

Keep the current sampling/download/upload sequence and all copy. Apply the shared form system, tokenized file drop, progress/results surfaces, semantic validation states, and responsive two-stage workflow layout without changing `gt.js`.

- [ ] **Step 5: Run Report/GT regression checks**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests report gt -v 2`

Expected: PASS.

Run: `rg -n "#3b82f6|#2563eb|#eff6ff|#dbeafe" django-app/report/static/report django-app/gt/static/gt`

Expected: no legacy action-blue palette remains except a documented semantic focus color.

- [ ] **Step 6: Commit the Report and Manual GT migration**

```bash
git add django-app/lunit_audit/tests.py django-app/report/templates/report/report.html django-app/report/static/report/report.css django-app/gt/templates/gt/index.html django-app/gt/static/gt/gt.css
git commit -m "feat: restyle PRIMER audit reporting workflows"
```

---

### Task 5: Whole-Application Verification and Polish

**Files:**
- Modify if verification exposes defects: files changed in Tasks 1-4 only
- Test: `django-app/lunit_audit/tests.py`

**Interfaces:**
- Consumes: all migrated screens and static assets.
- Produces: a behavior-preserving, responsive, accessible full-app visual migration with verified static and template contracts.

- [ ] **Step 1: Run Django checks and full tests**

Run: `cd django-app && python manage.py check`

Expected: no errors.

Run: `cd django-app && python manage.py test -v 2`

Expected: all tests pass.

- [ ] **Step 2: Verify static assets**

Run: `cd django-app && python manage.py findstatic img/primer-mark.svg fonts/space-grotesk-latin.woff2 fonts/ibm-plex-sans-regular-latin.woff2 fonts/ibm-plex-mono-medium-latin.woff2 css/base.css js/base.js --verbosity 2`

Expected: each asset resolves exactly once from project static assets.

- [ ] **Step 3: Verify selector preservation mechanically**

Run: `cd django-app && python manage.py test lunit_audit.tests.VisualMigrationSourceContractTests -v 2`

Expected: PASS for Upload, Tasks, Import, Viewer, Report, and Manual GT selector/copy contracts.

- [ ] **Step 4: Run copy and external-dependency audits**

Run: `git diff efffe29 -- django-app/templates django-app/upload/templates django-app/viewer/templates django-app/report/templates django-app/gt/templates`

Expected: template changes are limited to shell/layout/accessibility markup; existing visible strings are not rewritten.

Run: `rg -n "https?://|@import" django-app/static/css django-app/upload/static django-app/viewer/static django-app/report/static django-app/gt/static`

Expected: no newly introduced runtime font or CSS dependency.

- [ ] **Step 5: Perform browser checks with synthetic/empty application state**

At 1440×900 verify desktop sidebar, active navigation, main content width, Upload, Tasks, Import, Viewer, Report, Manual GT, modals, tables, and focus rings. At 390×844 verify drawer open/close/Escape/backdrop behavior, no page-level horizontal overflow, wrapped toolbars/actions, scrollable tables, and usable form controls. Confirm reduced-motion behavior through browser emulation.

- [ ] **Step 6: Fix only in-scope visual or compatibility defects and rerun checks**

For every defect, rerun the narrowest relevant contract test and then `python manage.py test -v 2`. Do not expand into backend or copy changes.

- [ ] **Step 7: Commit final polish if needed**

```bash
git add django-app
git commit -m "fix: polish PRIMER responsive visual migration"
```

- [ ] **Step 8: Confirm clean implementation state**

Run: `git status --short`

Expected: clean working tree, or only unrelated pre-existing user changes.
