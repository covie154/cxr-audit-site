# Quick task 261007-i5n — complete

Removed fixed grid-row spans and minimum row height from published cards; preserved configured widths and aligned cards to their own content. Removed the value-card row override. Charts use a 360px canvas, compact grid margins and bottom scrollable legends. Line chart visible date labels show bucket starts to avoid clipped range labels; tooltips retain full bucket labels.

Validation: 72 JavaScript tests passed. Affected Python run covered 29 tests; browser checks (including new <=26px card bottom gap and >=250px plot height regression), routes and responsive 1440/1024/390 checks passed. The only remaining fixed-markup assertion was updated and all 16 page tests passed on rerun. git diff --check passed. Browser preview refreshed and left open with compact table cards and taller graphs. No clinical data accessed.

Code commit: 8fcc977.
