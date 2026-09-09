---
status: complete
---
# Login centring fix

Removed the inherited 236px sidebar margin from guest workspaces. Existing login flex centring now uses the full viewport width.

Commit: 3a2fc0b

Validation: Local Chromium with the real base/login styles and login markup measured zero horizontal and vertical card offset at 3605x2020, 1920x1080, 1024x768, 900x768, and 390x844. Authenticated desktop margin still matches --nav-w (236px). The initial verification used an incorrect hard-coded 244px expectation; corrected to compare against the actual design token and passed. git diff --check passed.

No live deployment performed. Unrelated concurrent working-tree changes were left untouched.
