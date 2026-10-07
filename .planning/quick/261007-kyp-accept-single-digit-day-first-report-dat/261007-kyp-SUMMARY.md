---
status: complete
---
# Completed

Shared date parser accepts one- or two-digit days/months and two- or four-digit years, with matching slash or hyphen separators. Two-digit years map to 2000-2099; four-digit years remain literal. Both fields and native pickers receive padded ISO values for server validation. Relative tokens are preserved.

Screenshot input 5/4/2026 and follow-up 5/4/26 resolve to 2026-04-05. Fourteen focused JavaScript checks passed; syntax and diff checks passed. Commits: f337951 and c032b79.
