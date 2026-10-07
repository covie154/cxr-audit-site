---
status: complete
---
# Completed

From and To show YAML defaults and accept independent D/W/M/Y minus-offset expressions or fixed dates. D remains the latest complete eligible study date; W resolves to Monday, M/Y to the first day in both fields. Calendar Grouping is available on every card, retaining YAML buckets; unbucketed cards default to Overall. Non-line displays reuse existing renderers per nonempty period and preserve comparisons, filters and the original study anchor. Snapshot/print/email tables retain period results. Non-line grouping is bounded to 100 populated periods; choose a coarser grouping for longer spans.

Fixed dates display as DD-MM-YYYY and accept DD-MM-YYYY or DD/MM/YYYY. Both fields include an accessible native date picker; picker/text synchronization preserves relative expressions. YAML and transport dates remain ISO. Reset restores YAML defaults. No dependencies added or clinical data read.

Validation:
- Full report suite: 466 tests passed, one skipped (before final picker addition).
- Subsequent snapshot/grouping/showcase checks: 31 passed, including independently relative boundaries frozen through print.
- Final picker/date/default/page checks: 37 passed.
- Final Chromium browser suite: 8 passed; native picker activation and date submission tested, desktop/tablet/mobile layout checks passed. Synthetic evidence: date-controls-picker-1440.png in the existing temporary browser evidence directory.
- Final JavaScript suites: 77 passed. Syntax and git diff checks passed.

Commits: c9a037b (date resolution/grouping), 75a8d93 (day-first formatting/pickers). Concurrent session commit eac294a included this task's initial From/To template and collection changes while disabling categorical Group by for pie/confusion cards; its changes were preserved. Calendar Grouping remains available on those cards.

GSD execution was inline per the Codex adapter; the actual repository root already contains django-app/.git-equivalent root metadata and .planning, matching IDE paths. Initial broad suite run from the repository root hit three existing relative-path test assumptions; rerunning from django-app passed. The new template test uses test-only static storage.
