# Quick task 261007-jby — complete

Matching and Reference lines share family, size, weight, line height and margins. Include groups now uses a native auto popover with a compact checkbox list, Select all/Clear and bounded scrolling. Positioning keeps the menu within the viewport; it overlays content without increasing card height. Escape and outside-click dismissal are native; switching to None closes any open menu.

Validation: 23 page/browser tests passed, including identical computed metadata fonts, unchanged card height with the dropdown open, bounded menu height and Escape dismissal. Responsive 1440/1024/390 checks passed. All 72 JavaScript tests passed; git diff --check passed. Synthetic preview refreshed, dropdown opened/dismissed successfully and tab left open. No clinical data accessed.

Code commit: 8e2da08.
