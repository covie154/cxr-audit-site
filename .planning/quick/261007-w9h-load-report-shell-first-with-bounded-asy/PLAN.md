# Quick task: progressive report loading

Render published report shell without study reads; retain synchronous editor previews. Load visible cards first with at most three requests, reusing signed widget endpoints and stale response protection. Keep results during updates, surface initial failures, and prevent raw table formatting flashes. Verify shell performs no study reads, request queue drains after failure, and existing widget/security regressions.
