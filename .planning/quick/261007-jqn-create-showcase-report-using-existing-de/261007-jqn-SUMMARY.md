# Quick task 261007-jqn — complete

Created seed/showcase.v1.yaml with all seven implemented displays: number, summary table with Overall, line, categorical bar, pie, binary confusion matrix and horizontal boxplot. Uses the same PRIME adapter and current project dataset. Registered existing categorical/matrix measurements in the production project catalog and mapped category inputs through configured physical sources. Categorical grouping supports Site/Age and explicit None. Binary matrices retain both classes for single-class selected populations. Count bars now use a zero baseline.

Published showcase@r1 through the existing definition repository at the configured private definition root; other reports preserved. No clinical rows were read and no alternate dataset was installed. The temporary preview uses its existing synthetic seam for both reports, and Showcase is listed and open for review. User follow-up: Clear default label shortened and action right-aligned.

Validation: full report suite 461 tests passed (one skipped); final Showcase/navigation tests 5 passed; 72 JavaScript tests passed and the count-bar baseline assertion passed in the renderer suite. Strict Showcase publication and all seven payloads checked across None/Site/Age. Browser verified all cards, list/default navigation and shortened Clear default. git diff --check passed.

Code commit: 7de0f26. Published definitions are deployment-local; packaged seed can be published through the existing editor elsewhere.
