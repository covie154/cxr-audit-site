---
status: complete
---
# Table pagination
Replaced Show more and duplicate page text with a Previous / Next footer outside the scrolling table body. Displays row ranges, disables boundary buttons, resets scroll on navigation, blocks clicks while loading, and resets Apply to page one. Small summary tables remain unpaged.

Navigation reuses a 60-second private per-worker memory cache keyed by user, session, signed publication context and request scope, after all authorization and override validation gates. Maximum 16 entries and 2 MiB serialized per entry; oversized results use the uncached path. First-page Apply refreshes results. Detail rows retain the existing 100-page limit.

Database-side slicing was not introduced: Python clinical classification, latest-date anchoring and full-population statistics must run before selecting detail pages. This change removes repeated reads/evaluation on navigation cache hits without duplicating those semantics in SQL. Cache misses across workers and after expiry still evaluate the full population.

Validation: 18 published-page/backend tests; 62 JavaScript renderer/state tests; real Chromium synthetic 120-row navigation test covering first/middle/last pages, Previous, Apply reset and footer containment; JavaScript syntax checks and git diff --check. Existing deployment warnings about HTTP LLM endpoint and missing staticfiles directory occurred in test settings.

The stylesheet also retains the preceding heading-card padding/font correction.
