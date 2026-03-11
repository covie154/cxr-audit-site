# Fixes 3 & 4: File Remove Button Placement and Header Username/Logout Placement

## Issue 3: File Remove Button Placement (Upload App)

### Problem
In the Upload app, when files are selected, the "Remove" button appeared above the file name rather than beside it on the same row. The Manual GT app had the correct layout for comparison.

### Root Cause
The `handleFiles` function in `upload.js` wrapped both the file summary text and the nested file list inside a single `<div class="file-info">`. Because this was a block-level `<div>` containing a tall `.file-list` element, the flex container (`.file-selected`) placed the remove button aligned to the center of the entire tall block, visually displacing it above the file names.

In the GT app, the file info is a `<span>` (inline) sitting beside the remove button, with no nested block content -- so both elements stay on the same row.

### Fix
- Changed `upload.js` to use a `<span class="file-info">` for the summary text (file count and size), with the remove button as a sibling, and the `.file-list` div placed after both as a separate element.
- Added `flex-wrap: wrap` to `.file-selected` in `upload.css` so the file list wraps to a new line below the name/button row.
- Added `width: 100%` to `.file-selected .file-list` to ensure the file list takes the full width on its own line.

### Files Modified
- `django-app/upload/static/upload/upload.js` (lines 99-101)
- `django-app/upload/static/upload/upload.css` (`.file-selected` rules)

---

## Issue 4: Header Username/Logout Placement

### Problem
On desktop, the Username and Logout button appeared below the navigation menu items instead of to the right of the header bar. Mobile layout was already correct.

### Root Cause
The `.nav-collapse` wrapper (containing both `<nav>` and `.header-right`) had no `display: flex` on desktop. As a plain `<div>`, its children stacked vertically. The `.header-right` had `margin-left: auto` which only works in a flex context, so it had no effect.

### Fix
- Added a desktop rule for `.nav-collapse` with `display: flex`, `align-items: center`, and `flex: 1` so it fills the remaining header space and lays out its children (nav + header-right) horizontally.
- Added `flex: none` to the mobile `.nav-collapse` override to prevent the desktop `flex: 1` from interfering with the mobile column layout.

### Files Modified
- `django-app/static/css/base.css` (added `.nav-collapse` desktop rule, updated mobile override)

---

## Reflections
- Both issues stemmed from missing or incorrect flex container configuration. The upload file display used a block-level wrapper where an inline element was needed, and the header relied on `margin-left: auto` without a flex parent to make it effective.
- The GT app served as a good reference implementation for the correct file selection pattern. Matching the upload app to use `<span>` instead of `<div>` for the file info, plus `flex-wrap`, keeps the remove button on the same line as the summary while allowing the detailed file list to wrap below.
- The header fix is minimal: a single CSS rule addition on desktop, with one property override on mobile to preserve existing behavior.
