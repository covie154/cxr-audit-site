---
status: complete
---
# Report-name heading and editor URL

Primary heading and document title now read Editing: <report title>. Canonical editor slugs derive from report names (Analysis Report -> /layout/editor/analysis_report/); catalog and create links use the canonical URL. Existing definition-ID URLs redirect to it. Stored definition IDs, draft save/delete identity and publication versions are unchanged. Duplicate titles and collisions with existing IDs are disambiguated deterministically.

Verification: 25 editor tests passed, including canonical redirect, heading, stable identity, non-admin denial and duplicate title/ID collision coverage. Existing isolated browser navigation regression passed against synthetic data. Live localhost browser verified /layout/editor/overview/ redirects to /layout/editor/analysis_report/, h1 is Editing: Analysis Report, underlying ID stays overview, and catalog link uses the canonical name URL. Diff whitespace check passed. Restarted preview; clinical data was not changed.
