---
status: resolved
trigger: Single values scroll in short wide cards; editor action buttons overlap resize corner.
created: 2026-10-07
updated: 2026-10-07
---

## Evidence
On the actual Showcase page the body is 156px high with scrollHeight 159px. The number line box is 125px, but its scrollHeight is 143px. Font glyph overflow plus centring exceeds the body. Existing fitting checks only the line box height.
Editor CSS pins actions bottom-right next to the resize handle instead of the original centred alignment.

## Current Focus
Measure full text scrollHeight in the existing width/height fit; centre ordinary editor actions and preserve heading/divider actions.

## Resolution
Use number.scrollHeight in the existing two-axis binary fit. Centre actions; cards with content height at least 180px place actions below the centred icon and label. One-row cards retain their bottom position.
Verification: value_card_check.py passed nine width/height combinations and editor positioning. git diff --check passed. Preview server 8766 restarted; temporary harness given serializable synthetic user/session identity for current view cache scope.
