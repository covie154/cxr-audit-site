---
status: complete
---
# Grey admin-only Edit layout button

Moved the admin-gated editor link directly after Email report, with a grey fill and border. Removed the separate admin row. Existing admin authorization is retained.

Validation: all 16 report_v2.tests.test_pages tests passed; git diff --check passed.
Code commit: 1b9bba9.
Existing unrelated working-tree changes were preserved.
