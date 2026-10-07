---
status: resolved
trigger: Heading cards show a scrollbar; title should fit one row.
created: 2026-10-07
updated: 2026-10-07
---

## Evidence
The report page card selector applies 24px padding, overriding the later 16px frame selector. A 64px single-row heading cannot contain 48px padding plus its heading line. Page h2 margin adds further overflow.

## Resolution
Set heading-specific padding to 8px 16px and title font to 1.25rem with line-height 1.25 and zero margin. Keep overflow handling for longer headings.
Verification: run heading_card_check.py with Chromium against the actual stylesheet, desktop and mobile, quarter-width and full-width cards.

