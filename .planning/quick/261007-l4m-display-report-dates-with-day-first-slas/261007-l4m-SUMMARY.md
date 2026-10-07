---
status: complete
---
# Completed

Report date fields now display DD/MM/YYYY for YAML defaults, picker choices and typed fixed dates on blur. Relative tokens remain literal; flexible inputs and ISO transport remain intact. Visible table dates, chart period labels, coverage and print/email window/anchor dates use day-first slashes.

The local synthetic preview at 127.0.0.1:8766 was serving code loaded before recent controls; verified its command and synthetic-only data adapter before restarting it. Chromium verified 12/12/2025, two visible calendar icons and native showPicker activation. Screenshot: C:/Users/covie/AppData/Local/Temp/primer-date-controls-slashes.png. No clinical data accessed.

Validation: 81 JavaScript checks passed; 58 affected Python checks passed; 8 browser checks passed, including native picker activation and mobile/desktop layout. Presentation expectations updated while ISO payload assertions retained. Diff checks passed. Commit: 969424e. Unrelated concurrent editor/navigation changes left untouched.
