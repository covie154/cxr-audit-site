# Quick task 261007-glk — complete

Implemented project-defined Group by and Include groups on every packaged PRIME card, independent selection state, all/clear, explicit None, and configuration-defined age bands. Adapter mapping and labels remain project-owned; published card allow-lists and group bounds remain enforced.

Grouped values, table summaries, time series, case tables and boxplots reuse existing evaluators. Summary tables include pooled Overall rows and V1-style headers/separators. Empty populations skip measurement dispatch so clearing groups produces empty cards instead of classification errors. Print/email snapshots preserve selection state.

Validation: 451 Django tests passed (one skipped), 71 JavaScript tests passed, git diff --check passed. Browser checks covered 1440/1024/390 widths; synthetic preview verified age selection, clear, independent cards and Overall appearance. Preview restarted and left open at http://127.0.0.1:8766/report/overview/. No clinical datasets accessed.

Code commit: 500e20a. Existing published definitions retain their allow-lists; re-publish the updated seed to enable Site/Age on all cards there.
