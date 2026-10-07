# Quick task 261007-ha1 — complete

Native card-title disclosures hide controls, coverage and Reference text initially. Include groups is a checkbox dropdown beside Group by in a single horizontally scrollable control row. Number-card normal subtext remains hidden; errors open settings automatically. Table captions retain screen-reader access.

Range remains distinct from Window: explicit From/To dates or anchor-relative D/W/M/Y presets select the population; Window chooses day/week/month/year calendar buckets on time-series cards. Validated time_grouping passes through live updates and frozen print/email exports. Removed fixed weekly labels from seed chart titles.

Validation: complete Django report suite 454 tests passed (one skipped), 72 JavaScript tests passed; seed suite 28 tests passed after title changes. Browser layout checks at 1440/1024/390 passed with opened settings and scroll-row containment. Live synthetic preview verified collapsed cards, Include groups dropdown and monthly time grouping without date-range changes. Final preview refreshed and left open on localhost:8766. No clinical data accessed.

Code commits: 68c1e1c, b02e1b6. Existing published layouts retain their definitions; re-publication is required for updated seed configuration/titles.
