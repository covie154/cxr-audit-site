---
status: complete
---
# Single-value card sizing

Fit actual text to the available body dimensions with the existing resize lifecycle. Centre below the heading using CSS; server-rendered values have responsive CSS sizing. Grouped values retain their layout.

Validation: all 16 Node renderer tests pass. Synthetic Chromium check confirms centring within 1px, font growth from 63.9px to 129.4px on card widening, and no overflow for long counts.

Code commit: 7a0164d. Unrelated working-tree changes preserved; CSS staged selectively.
