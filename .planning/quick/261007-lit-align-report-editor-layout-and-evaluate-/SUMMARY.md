---
status: complete
---
# Editor layout and live draft preview

Reused site design tokens, standard buttons, responsive cards and report widget renderers. Main actions sit with YAML, validation/preview alongside on desktop and below on mobile; bundled seed tools are in Starter templates with replacement behavior explained. Removed both requested messages.

Preview validates the submitted YAML, evaluates its first widget through views._evaluate and the real data adapter, and renders the existing widget component instead of JSON. Data failures return a generic message without exposing exception values. Preview still writes no draft/publication and sends no mail.

Local preview helper now reads the configured django-app/db/db.sqlite3 through a Windows UNC read-only SQLite URI. Removed synthetic study fetching. Runtime definitions remain in its separate temporary root and the preview admin identity is unchanged. Published temporary definitions override seed fallback definitions in the report viewer. No production account or clinical database modifications.

Verification: 61 Django editor/seed/page tests passed; JavaScript navigation regression passed; diff whitespace check passed. Chromium verified live first-widget count (4571 matching and eligible), no page errors, report selector navigation, and no horizontal overflow at 1440/1024/390 widths. Configured study count checked without outputting clinical records (11159). Existing LLM HTTP and collected-static warnings persist.
