# Summary

Completed viewport-filling YAML workspace with internal scrolling, compact validation callout beside save status, and wide native preview dialog. Card selection updates preview automatically; stale preview responses are ignored.

Fixed validation display: background card validation previously discarded schema errors, and saving a draft unconditionally cleared them. Validate on load and after edits; draft-save responses include validity and all schema error paths. Saving incomplete work remains allowed, while publishing rejects it. Empty layout.height and ci.enabled both appear in the callout.

## Verification

- Django editor/repository: 38 tests, passed with one platform-specific skip.
- Node editor checks: save retains schema errors, automatic card preview, stale-response protection passed. Concurrent visual-tab check also passed.
- Isolated browser layout regression passed before concurrent visual-tab changes.
- Live browser: null height and ci.enabled flagged during editing, retained after save and reload; publish returned 422; viewport had no page scrolling; disposable report deleted.
- Prior viewport checks: desktop, mobile and short landscape fit without document scrolling; preview opens wide and closes correctly; selecting a different card renders it automatically using live aggregate data.

Concurrent visual-editor tab work shares the editor files and is preserved. No clinical dataset contents were printed or committed.
