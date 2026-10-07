# Visual report layout editor — implementation plan

Date: 7 October 2026
Status: Implemented; synthetic regression and browser verification recorded in visual-editor-execution/SUMMARY.md

## Purpose

Let less technically confident administrators create and arrange reports without writing YAML. Keep the interface focused on cards and use the existing draft, preview, and publication workflow.

This document extends EXECUTION-RUNBOOK.md for the visual editor. The packaged schema and application validators are authoritative where older planning documents describe proposed behavior.

## Agreed scope

- Visual editor remains the default tab; YAML editor remains available.
- Keep existing sections and their order. Display their headings and cards; do not add section creation, renaming, deletion, or reordering controls.
- Add and reorder cards within a section. Moving between sections is outside this version.
- Add card opens a dropdown with icons and friendly card type names.
- Drag cards to reorder them; drag a corner handle to resize them. Snap to the report grid and reflow automatically.
- Each new card starts with a preset width and height. Existing cards retain their declared sizes.
- Dynamic cards display their header and an icon identifying the display type, rather than live clinical results in the canvas.
- Hover reveals Edit and Preview. Also expose these actions on focus and selection/tap so touch users can use them.
- Edit opens a guided options panel and includes width and height fields.
- Preview opens the existing preview dialog with that card selected, using the current unsaved draft.
- Include undo for completed card changes.
- Keep the existing Save draft, Preview, and Publish buttons. No autosave or additional save/publish workflow.
- YAML is the source of truth; visual changes and YAML changes operate on one draft.
- No additional keyboard rearrangement interface. Keep ordinary focus, labeled controls, and accessible buttons.

## Canvas and layout

Use the existing 12-column report grid. Widget array order determines reading order. Do not introduce x/y coordinates, absolute positioning, freeform overlaps, or a second saved layout representation.

Reordering changes only the widgets array in the current section, preserving stable widget IDs. Show a insertion marker before dropping. A canceled drag changes nothing. Cards following a move or resize flow into available rows in the same way as the rendered report; do not use dense packing that changes reading order.

Resize snaps width to integer column spans from 1 through 12 and height to integer row counts from 1 through 30, matching the current schema. Respect grid.row_height_px. Clamp values and reject invalid manual size entries with a friendly message. Size presets are starting values, not fixed widths.

Use a clearly visible move handle and resize handle. Editing, selecting text, or clicking action buttons must not initiate dragging. Commit a drag/resize as one change on release; cancel restores the original layout. Support mouse and touch through native pointer events.

On narrow screens, stack cards and use the options panel to change stored sizes. Do not let a narrow viewport silently rewrite desktop widths. Heights remain minimum heights; tables and text can grow without cropping content.

Proposed new-card presets (implementation defaults, not schema restrictions):

| Type | Width | Minimum height |
|---|---:|---:|
| Value | 3 | 3 |
| Table | 12 | 5 |
| Line chart | 6 | 4 |
| Bar chart | 6 | 4 |
| Pie chart | 6 | 4 |
| Confusion matrix | 6 | 4 |
| Box plot | 6 | 4 |
| Static text | 12 | 2 |
| Divider | 12 | 1 |

## Adding and editing cards

Put Add card in each existing section so the destination is obvious. Choosing a dynamic type opens its configuration guide; do not insert an incomplete card into the authoritative YAML before Apply. Cancel leaves the draft unchanged.

Use one options panel with these steps:

1. Content: card title and what to measure, or plain text for a static card.
2. Display: compatible card type and relevant display options.
3. Optional settings: date window, permitted filters/comparison, confidence intervals, columns, benchmarks, and other settings supported by that measurement/display.
4. Size: width and minimum height, with friendly presets and numeric options.

Use existing project catalogs and validator metadata for choices. Show friendly labels, explaining unfamiliar terms; do not require users to type measurement IDs, source IDs, policy references, or expressions. Limit choices to compatible combinations without inventing clinical defaults. Required measurement inputs and policy references must be supplied before Apply. Explain validation errors next to the relevant controls.

Apply creates one undoable YAML change. Cancel discards panel edits. Preserve fields that the panel does not expose. Changing card type must not silently discard incompatible settings: show what will change before applying. Deleting a card is undoable; disable deletion of the last card in a section while the schema requires at least one widget. Duplicate is outside the agreed first version.

For Preview inside an edit panel, validate a temporary candidate definition and preview that card without committing the panel changes. Preview on the canvas uses the current YAML draft. Closing preview returns to the same editor state.

## YAML synchronization and undo

The current YAML textarea holds the authoritative unsaved draft. A parsed document is a transient projection for rendering and editing, not a second persistent source. All visual operations serialize back to this draft and trigger the existing dirty tracking, validation, and card-list refresh behavior.

Reuse the strict server loader and semantic validators. Prefer a small admin-only, CSRF-protected read/transform path using the already installed Python YAML stack over adding a browser parser or attempting YAML parsing with regular expressions. Determine the smallest endpoint change after tracing editor_preview and repository validation. Transform requests carry current YAML and an explicit permitted operation; the server validates the operation and returns candidate YAML and the canvas projection without saving or publishing.

Successful transforms preserve section/widget identity, unrelated settings, and scalar meaning. A visual serialization may normalize formatting and remove YAML comments; document this limitation in the editor before the first visual edit. Do not promise byte-preserving round trips with the existing YAML parser.

Valid YAML edits rebuild the visual canvas. Invalid YAML remains untouched in the textarea, shows a friendly error, and pauses visual mutations; any retained last-valid canvas is clearly marked stale. Distinguish a parsing/structural failure from a card-level semantic error where feasible: an inspectable card may still offer editing to correct its settings, but validation remains required before applying or publishing. Never silently replace invalid YAML with the previous valid version.

Avoid stale responses: apply a projection/transform only if it still corresponds to the current YAML and latest request. A slow response must not overwrite a newer edit. Disable conflicting visual mutations while a transform is pending. Preserve server revision-conflict behavior.

Undo stores prior YAML snapshots in browser memory only. One completed add, delete, edit, reorder, or resize is one history entry. Group manual YAML typing into meaningful edits rather than each keystroke; undo restores YAML and rebuilds the canvas, including invalid draft states. Keep a bounded history (proposed: 50 entries); clear it on report navigation/reload. Saving does not clear history; undo after saving marks the draft dirty. Undo never rolls back a published version or changes the saved revision token. No persisted history or redo requirement in this version.

## Static text and divider support

Current application schema permits value, table, line, bar, pie, confusion_matrix, and boxplot. Static text and divider are new report types, not merely editor decorations.

Extend the schema with type-specific rules: static cards require layout and stable identity but no measurement, query, date window, filters, or clinical evaluation. Text is plain escaped text with preserved line breaks; arbitrary HTML and Markdown are outside scope. Dividers have no dynamic preview or data query. Preserve compatibility for existing schema_version: 1 reports and mirror the application schema changes in the planning contract.

Implement these types across interactive reports, the preview dialog, print/PDF HTML, and email rendering before exposing them in Add card. Static text previews locally/render-only; divider previews render its appearance. Dynamic card evaluation and aggregate/case-data boundaries remain unchanged.

## Implementation sequence

1. YAML projection and mutations: trace the existing editor flow; add validated in-memory transforms, synchronized canvas state, stale-response protection, and snapshot undo. Add focused security and round-trip checks.
2. Canvas and guide: render existing sections and card summaries; implement Add card, options editing, deletion, size fields, and selected-card preview with compatible catalog choices.
3. Layout interaction: add within-section drag ordering, snapped resizing, automatic reflow, responsive behavior, and one undo entry per completed gesture.
4. Static types: add schema/validation and report, preview, print, and email support; expose Text and Divider only when all outputs work.
5. Verify the complete workflow using synthetic reports and the existing test/browser tooling. Record evidence and update implementation notes.

Each step uses the required GSD workflow and preserves existing user edits. Do not treat the current Visual editor placeholder as a completed editor.

## Likely integration points

- django-app/report_v2/templates/report_v2/_editor_form.html: canvas, actions, and guided options panel.
- django-app/report_v2/static/report_v2/editor.js and editor.css: shared draft state, tabs, preview selection, interactions, and styling.
- django-app/report_v2/admin_views.py and editor_urls.py: authorized projection/transform integration if needed.
- django-app/report_v2/definitions/: strict YAML loading, structural and semantic validation, and serialization.
- django-app/report_v2/definitions/schemas/report.schema.json: static type rules.
- Existing report widget registry and interactive/print/email templates: static rendering and layout consistency.
- report_v2 tests: reuse current synthetic fixtures and test runners.

Reuse these integration points; split a module only where the implementation becomes easier to maintain. No new grid library, framework, database model, or frontend dependency is planned.

## Acceptance checks

- Existing reports load without size/order/setting changes; opening or switching tabs never marks a clean draft dirty.
- Add and Edit guides produce validator-approved YAML with unique stable IDs; Cancel changes nothing.
- Reordering cannot leave its section; resize clamps to schema bounds and retains preset widths until changed.
- Automatic reflow preserves YAML reading order and matches report output; content is never cropped to enforce height.
- Card Preview selects the intended ID and reflects unsaved YAML; no save, publication, email, or clinical-data export occurs.
- Undo restores prior YAML after every supported mutation and after manual YAML edits, with correct dirty state.
- Invalid YAML is preserved and blocks unsafe visual mutation; slow responses cannot replace newer changes.
- Visual transforms preserve settings outside the edited card, and options outside the displayed form.
- Text is escaped and dividers/text render correctly across report, preview, print, and email.
- Admin-only access, CSRF protection, strict loader limits, friendly error handling, and revision conflicts remain enforced.
- Pointer operations work on mouse and touch; actions remain usable without hover; basic control accessibility is preserved.

Use focused Node tests for editor state/undo and gesture completion, Django tests for transformations/validation/static types, and the existing synthetic browser suite for drag, resize, preview selection, and output parity. Do not read production datasets, migrate production databases, publish production seeds, or send real email for verification.
