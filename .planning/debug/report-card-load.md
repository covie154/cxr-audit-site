---
status: investigating
trigger: All cards fail in local preview after progressive loading
---
# Evidence
Local preview is temporary ThreadingHTTPServer helper, with mocked request authentication. Single widget POST returns 200/ok. Investigate concurrent transport and renderer exceptions; generic catch currently hides both.

# Resolution and limits
Fresh reload of the authorized local preview showed study counts and rounded percentages. Single and concurrent widget endpoint requests returned JSON status ok. The original cause could not be reproduced after reload; no claim of a confirmed backend root cause. Removed temporary console diagnostics. Hardened shared response handling to show safe HTTP status for non-JSON responses, expired-session guidance for redirected HTML, distinct connection error, and separate rendering error. No raw response bodies or clinical data logged.

Verification: 24 JavaScript regression tests pass, including non-JSON HTTP 503 handling. Live local preview verified after reload.
