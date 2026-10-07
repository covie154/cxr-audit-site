---
status: complete
---
# Compact report card settings

Value widgets and configured widths below 3/12 omit the settings form. Wider non-value cards retain settings, with 12px labels, 13px control text and tighter spacing. Definition defaults and API behavior remain intact. Table pagination works without the settings form.

Validation: six database-free Django routing/template tests and seven JavaScript state tests passed, including pagination with no form. Synthetic browser preview confirmed the width-2/width-3 cutoff and no desktop/mobile overflow. Actual UAT data and export operations were not exercised. Initial preview navigation used stale cached markup; fresh navigation and cache-busted CSS verified the current source.

Implementation commit: 918575c.
