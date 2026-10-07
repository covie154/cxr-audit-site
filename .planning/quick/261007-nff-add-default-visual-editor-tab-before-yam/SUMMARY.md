---
status: complete
---
# Report editor tabs

Visual editor is the default first tab with an honest placeholder for upcoming visual layout controls. YAML editor is the second tab. Shared save, preview, publish, revision and validation controls remain available. Tab switching keeps the same textarea and supports arrow keys, Home and End.

Changed: _editor_form.html, editor.js, editor.css and tests/js/editor_navigation.test.mjs.

Validation: Node regression suite 4/4 passed; node --check passed; git diff --check passed.

Deviation: Actual Git root is the supplied workspace (not a nested django directory). Changes remain uncommitted because all four editor files already contained user work; no unrelated changes were staged or committed.
