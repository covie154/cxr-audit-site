---
status: complete
---
# Progressive report loading

Published reports return skeleton cards without study reads; visible cards load first with a three-request queue. Existing results remain during updates; cancellation, stale guards, error handling and export settlement reuse existing endpoint/state contracts. Tables first appear through the formatted browser renderer. Editor previews retain synchronous evaluation. No persistent clinical-data cache or new dependency.

Validation: 23 JavaScript tests and 46 focused Django tests passed. Broad report suite ran 499 tests with one skip; two outdated initial-HTML assertions failed and were updated. Both replacements passed, including Chromium date-picker/card-update coverage. Remaining broad-suite cases passed. Existing HTTP LLM configuration/staticfiles warnings remain.

Backend full-table reads per widget remain a separate optimization. Concurrent value-card and heading styling edits were excluded from this commit.
