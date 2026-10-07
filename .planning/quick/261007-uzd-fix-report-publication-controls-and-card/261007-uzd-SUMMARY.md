---
status: complete
---
# Report publication controls and card heights

Commit: `24d45f0`.

Implemented publishing progress and navigation to the report; state-aware Publish/Unpublish and View report controls; catalog publication actions; locked unpublish retaining editable drafts and immutable history; monotonically advancing republish versions. Unpublish preserves unsaved editor changes. Published and preview cards honor configured row count and row pixel height, scrolling content when needed. Toolbar Add card inserts after the selected row, defaulting to the last row, through existing options and undo handling.

Sections are existing YAML heading groups from the report seed, not newly introduced by the toolbar change. Report URL matching now accepts repository-supported hyphenated IDs used by existing publication tests.

Validation: 51 focused Django tests passed; 5 Node tests passed; 3 visual-editor Chromium tests passed, including custom 80px row heights, row insertion, preview/report height equality and publish/unpublish. Responsive browser overlap check passed at 1440, 1024 and 390px. JavaScript syntax and git whitespace checks passed. All test data synthetic and storage temporary. Browser harness logs now write to its temporary server.log rather than an unread pipe that blocked longer suites. Existing LLM HTTP configuration warning unchanged.
