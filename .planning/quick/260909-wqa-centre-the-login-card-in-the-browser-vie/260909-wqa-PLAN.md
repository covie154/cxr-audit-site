---
mode: quick
status: planned
---
# Centre the login card in the browser viewport

## Task
- File: django-app/static/css/base.css
- Action: Remove the inherited sidebar margin from the guest workspace with a scoped CSS override. Preserve the authenticated layout and existing login sizing.
- Verify: Check guest card geometry at desktop and mobile sizes, authenticated sidebar spacing, and git diff whitespace.
- Done: Guest login is centred on both axes whenever the card fits the viewport.
