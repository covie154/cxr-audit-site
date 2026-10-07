# Table pagination
Replace Show more and renderer page text with an accessible Previous / Next footer outside the scrolling body. Retain 50 rows and reset page on Apply. Keep bounded summary tables unpaged.
Avoid repeated full-population evaluation for page navigation using a private bounded 60-second memory cache keyed by user, published context and validated overrides. First-page Apply refreshes the cache. Preserve clinical classification, anchors and aggregate counts; database slicing before these computations would change semantics.
Verify real browser navigation/footer bounds and backend cache isolation/refresh/page data. Preserve existing worktree edits; commit only this task.
