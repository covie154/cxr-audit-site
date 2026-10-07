---
status: complete
---
# Quick task 261007-gb8

- Classification summary tables show all site groups under the existing 100-group bound; case lists retain pagination.
- Hidden pagination buttons respect CSS visibility. Synthetic preview contains only two sites, both already displayed.
- Box plots, outliers, duration labels and benchmark lines are horizontal.
- Local temporary preview launcher now dispatches widget POSTs to the real view and renders the legacy V1 landing page at /report-old/ instead of returning V2 for every GET. Launcher changes are outside Git, at C:/Users/covie/AppData/Local/Temp/primer-prime-preview.py. It remains a limited synthetic preview, not a complete Django server.
- Verification: 20 Django seed/page tests; 20 JavaScript renderer tests; browser Apply succeeded, no visible Show more on complete tables, horizontal plots inspected, V1 navigation verified.
- Existing environment warnings: HTTP LLM endpoint configuration and missing collected staticfiles directory. No clinical data accessed.
- Code commit: 78a219a.
- User approved this checkout's actual root Git/.planning boundary.
