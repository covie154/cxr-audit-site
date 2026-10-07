---
status: complete
---
# Admin report catalog and editor flow

/report/layout/ now lists report definitions for admins with edit, create and confirmed delete. Name/template dialog offers Basic report (valid Summary + record-count card boilerplate) or PRIME overview, saves a draft and opens its editor. Duplicate names cannot overwrite drafts. Policies are excluded from report lists. Detail editor uses Report V2 container spacing, removes All reports, keeps dropdown + create button, uses YAML editor heading, combines Revision/token and Draft/Published status, and uses No unsaved changes instead of Saved state: clean. Save remains manual; concurrent typing during save is preserved as unsaved.

Preview selects a draft card; validation-only requests refresh choices from edited YAML without fetching study rows. Foreign card IDs fail before data access. Existing registered renderers and real study adapter are reused. Bundled seed tools remain under explicitly named Bundled PRIME template.

Repository deletion checks draft revision and published version under the shared report lock, marks deletion before removing active draft/pointer, and preserves immutable published blobs. Save/create/publish reject deleted IDs to prevent stale-client resurrection. Admin, POST, CSRF, path validation and duplicate/conflict protections have focused tests. Clinical study data and account records were not modified.

Verification: 78 affected editor/repository/seed/page tests passed (one pre-existing platform-specific skip). JavaScript navigation regression passed. Chromium tested create -> edit boilerplate/add second card -> select second card/live preview -> save -> catalog -> confirmed deletion with no browser errors. Editor fits 1440/1024/390 and catalog fits desktop/mobile. Tested only a disposable report in the existing temporary definitions root; current study DB stays read-only. Restarted local preview server for final UI.
