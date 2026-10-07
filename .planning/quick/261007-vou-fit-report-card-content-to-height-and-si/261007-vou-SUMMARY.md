---
status: complete
---
# Flat report canvas, fitted cards and live Save

Code commit: `7beb40f`.

- Charts fill the available body height using existing ECharts resize observers; confusion matrices scale with CSS container units. New chart presets are six rows (seven for confusion matrices). Card padding is consistent, headings stay at the top, and editing controls remain inside small visual cards.
- Undo and Add card are adjacent; drag instructions are below them. Removed the Visual edits implementation note. Publish/Unpublish use the same minimum width. Save replaces Save draft and republishes valid edits to a published report. Invalid drafts remain private, and an expected publication version prevents Save from reversing a concurrent Unpublish.
- One canvas replaces section containers. Canonical YAML uses top-level widgets; legacy sections YAML remains readable and converts titles to collision-safe heading cards without losing card identity or order. Old report headings render as decorations until saved, preserving existing signed export state. Heading and divider presets are 12 columns by one row; dividers are plain horizontal lines. Heading cards work in previews and print/email exports.

Validation: full report-v2 run exercised 496 tests with one existing skip; two remaining legacy first-card assertions were updated for headings and both passed focused reruns. Five focused Chromium workflows passed (chart fit, confusion fit, visual operations, narrow canvas, publication cycle), plus a new Chromium check passed for heading/divider defaults, transparency and toolbar spacing. Six Node editor tests passed. Save/publish and stale-publication guard test passed. Syntax and whitespace checks passed. Tests used synthetic fixtures and temporary storage. Existing LLM HTTP configuration warning unchanged.

Restarted the existing interactive preview on port 8766. HTTP verification confirmed status 200, flat YAML, Save label, removed implementation note and heading support. Port 8765 remains stopped.
