---
status: complete
---
# Theme switch in sidebar

Moved the existing theme switch above the sidebar account row, shared with the mobile navigation drawer. Removed desktop top-bar space, retained the mobile hamburger header and full theme control, and moved the database record count into the page heading. Header height now resolves to zero on desktop so the database viewer uses the available height.

Validation: synthetic Django shell in headless Chromium at 1440, 900 and 390px passed placement, header visibility, theme switching, localStorage persistence, mobile label/switch visibility and Escape dismissal checks. git diff --check passed. No clinical data accessed.

Implementation commit: 5137845.
