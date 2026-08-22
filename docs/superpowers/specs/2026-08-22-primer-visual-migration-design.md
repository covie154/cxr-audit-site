# PRIMER-LLM Visual Migration Design

Date: 2026-08-22
Status: Approved in chat; pending written-spec review

## Objective

Apply the visual language defined by `documentation/primer-design/prototype/`
across the current Django PRIMER-LLM application. Replace the shared navigation
with the prototype's responsive application shell and restyle every existing
screen without changing user-facing text, workflow structure, application
behavior, permissions, or data presentation.

## Scope

The migration covers:

- the shared authenticated application shell and navigation;
- the login screen;
- Upload and Analyze;
- Processing Tasks;
- Import Historical Data;
- Database Viewer;
- Report;
- Manual Ground Truth;
- shared cards, buttons, forms, tables, badges, modals, toasts, progress
  indicators, and responsive behavior.

The Report page retains its current information architecture. The prototype
dashboard is a visual reference only in this phase; its mock layout, copy, and
data are not introduced into the production report.

## Non-goals

- No headings, labels, instructions, button text, status text, or other visible
  copy will be rewritten.
- No workflow, URL, view, model, form submission, filtering, export, upload,
  task, report, or manual-ground-truth behavior will change.
- No role or permission behavior will change.
- No React runtime or frontend framework will be added.
- No dashboard restructuring or new metrics will be introduced.
- No broad template component refactor will be performed.

## Visual Direction

The interface will follow the prototype's calm, high-trust clinical audit
language:

- cool slate neutrals for the canvas, surfaces, borders, and secondary text;
- clinical teal as the single action, link, and active-navigation color;
- green, amber, and red reserved for meaningful success, caution/discordance,
  danger, and abnormal-result states;
- Space Grotesk for headings, IBM Plex Sans for interface and body text, and
  IBM Plex Mono for numbers and identifiers that clinicians cross-check;
- restrained borders, shadows, corner radii, and motion suitable for long,
  data-dense review sessions;
- tabular numerals and compact table presentation for audit data;
- explicit, high-contrast keyboard focus rings.

The supplied PRIMER icon SVG will be copied into Django's static assets and
used as the application mark. Font files will be self-hosted as static assets,
avoiding runtime requests to third-party font services.

## Architecture

### Shared application shell

`django-app/templates/base.html` will own:

- a skip-to-content link;
- the supplied PRIMER brand mark and existing product name;
- a persistent 236-pixel desktop sidebar;
- the same existing navigation destinations and labels;
- the current role-based visibility rules for Tasks, Import, and Database;
- the current username and logout form;
- a compact top bar for page context and mobile navigation controls;
- an identifiable main-content outlet for child templates.

At narrow widths, the sidebar becomes an accessible drawer. The drawer control
will expose its state with `aria-expanded`, close on Escape and backdrop click,
and return focus predictably. The existing navigation destinations and logout
behavior remain unchanged.

The unauthenticated login screen will use the same brand system but will not
show authenticated navigation.

### Design tokens and shared components

`django-app/static/css/base.css` will define the authoritative production
tokens for color, type, spacing, radii, shadows, layout, focus, and motion. It
will also define shared presentation for cards, buttons, forms, tables, badges,
modals, toasts, and scrollbars.

Existing CSS custom-property names such as `--c-primary` will remain available
where page styles or JavaScript currently depend on them, but their values will
map to the new semantic palette. New descriptive aliases may be added where
they improve clarity.

`django-app/static/js/base.js` will contain only shell behavior. Existing
page-level JavaScript remains in place and its DOM selectors will be preserved.

### Page-level styles

Each existing page stylesheet retains ownership of page-specific layout and
states. The migration will:

- replace hard-coded legacy blues and inconsistent neutrals with shared tokens;
- align spacing, density, border treatment, and typography with the prototype;
- preserve all IDs and classes used by JavaScript;
- preserve the current DOM order and visible copy;
- add wrappers or classes only where needed for layout or accessibility;
- keep wide data tables horizontally scrollable;
- make toolbars and form actions wrap cleanly at smaller widths;
- retain usable pointer and touch targets.

Inline presentation styles will be moved to stylesheets only when required for
consistent theming. Dynamic inline values used for progress or server-rendered
state will remain functional.

## Behavioral Preservation

The implementation must preserve:

- Django template blocks and URL reversals;
- authenticated and admin-only navigation visibility;
- CSRF-protected logout and form submissions;
- all `window.PAGE_CONFIG` values;
- JavaScript-referenced element IDs, classes, and data attributes;
- modal, toast, upload, drag-and-drop, task, filter, pagination, report, export,
  and manual-ground-truth interactions;
- current displayed text and data formatting.

No view or model change is expected. A backend change is permitted only if a
test exposes a pre-existing rendering dependency that cannot be accommodated
in the presentation layer; such a discovery requires a scope review before the
change is made.

## Accessibility and Responsive Behavior

- Every interactive control must retain a visible keyboard focus state.
- Navigation controls will have accessible names and state attributes.
- Semantic landmarks will identify navigation and main content.
- Color will not be the only indicator for existing status components where
  the current text already provides a label.
- Motion will be subtle and disabled or reduced under
  `prefers-reduced-motion: reduce`.
- Desktop layouts will prioritize dense clinical workstations.
- At tablet and mobile widths, navigation becomes a drawer, toolbars wrap,
  grids collapse, and tables scroll rather than truncating data.

## Assets and External Dependencies

The implementation will not add a JavaScript framework or runtime CDN. The
PRIMER SVG and required WOFF2 font files will be stored under Django static
assets. Font licenses will be retained alongside the assets when required.

If the fonts cannot be obtained during implementation, the migration will use
the closest existing local fallbacks temporarily and report the deviation; it
will not add runtime calls to Google Fonts or another external font provider.

## Verification

Verification will include:

1. Run the existing Django test suite and any focused template/static tests
   added for the shell.
2. Verify the base template renders for unauthenticated, authenticated, and
   admin contexts without breaking URL reversal or permission-dependent links.
3. Verify static asset discovery for the icon, fonts, shared stylesheet, and
   shared JavaScript.
4. Check that all JavaScript selectors referenced by page scripts still exist
   after template edits.
5. Exercise representative pages and interactions in a browser at desktop and
   mobile widths, including sidebar/drawer behavior, upload controls, tables,
   modals, and report controls.
6. Compare representative screens against the prototype palette, typography,
   spacing, density, and semantic states.
7. Confirm through a template text review that existing visible copy was not
   intentionally altered.

## Implementation Boundaries

The expected application files are the shared base template, base CSS and JS,
login CSS, the six existing page templates, and their page-specific CSS files.
Page JavaScript should not require changes except where the new navigation
shell needs integration. Backend Python, database migrations, and clinical data
files are outside scope.

Implementation will proceed as a token-first migration: establish the shared
shell and visual primitives, migrate each page in place, then verify behavioral
and responsive compatibility across the application.
