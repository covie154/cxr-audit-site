# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused, database-free coverage for the report-v2 date-window / bucket layer (:mod:`report_v2.dates`).

These exercise the pure calendar entry points -- relative window resolution against the captured anchor,
explicit ISO overrides that stay verbatim, timezone-aware query boundaries, calendar bucketing independent of
the resolved range, and the anchor-provenance / no-today-fallback guarantees. They pin the runbook's Task-06
DONE-WHEN block and the "Calendar windows and fixed anchors" hand-check block:

* with anchor ``D = 2026-09-01`` (a Tuesday) the eight relative rows resolve to exactly
  ``D`` 2026-09-01..2026-09-01, ``D-7`` 2026-08-25..2026-09-01, ``W`` 2026-08-31..2026-09-01,
  ``W-1`` 2026-08-24..2026-09-01, ``M`` 2026-09-01..2026-09-01, ``M-1`` 2026-08-01..2026-09-01,
  ``Y`` 2026-01-01..2026-09-01, ``Y-1`` 2025-01-01..2026-09-01 -- all inclusive and all ending at ``D``;
* a ``W`` start is always a Monday and does not depend on the anchor's weekday;
* an explicit ISO range is returned verbatim -- even a future range -- never clamped toward the anchor, while a
  reversed range and an impossible calendar literal (``2026-02-30``) fail with typed errors;
* ``W``-start query boundaries are aware datetimes at local ``00:00`` / ``23:59:59.999999``; a Singapore local
  midnight of 2026-08-31 has a +08:00 offset and its UTC instant is 2026-08-30T16:00:00+00:00;
* buckets follow only the span, never the resolved window, and boundary buckets clipped by the span are ``partial``;
* the anchor is server-captured: a reader-submitted ``anchor``/``D``/``as_of`` is ignored, a subgroup narrowing
  never relocates the window (it is only reported as coverage), a newer *incomplete* row cannot advance ``D``,
  and an empty / nothing-complete candidate set yields ``None`` -- never a fabricated "today";
* the module is pure: no ORM/database token and no wall-clock call appears in its source or its globals.

No database, ORM, factory row or real/clinical data is touched: the whole suite is
:class:`django.test.SimpleTestCase`, the fixtures are literal ``datetime.date`` values (never the ``*_db``
builders nor ``upload.models``), and the production static / SSL / mail configuration is overridden away so the
suite is hermetic.
"""

from __future__ import annotations

import inspect
import types
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from report_v2 import dates as dates_module
from report_v2.dates import (
    Anchor,
    Bucket,
    InvalidDateLiteralError,
    InvalidOffsetError,
    InvalidTimezoneError,
    InvalidWindowError,
    MissingAnchorError,
    QueryBoundaries,
    ResolvedWindow,
    UnknownBucketError,
    bucket_range,
    capture_anchor,
    localise_day_end,
    localise_day_start,
    resolve_query_boundaries,
    resolve_relative_window,
    resolve_request,
    resolve_window,
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# The captured anchor every window test hangs off -- 2026-09-01 is a Tuesday (weekday()==1).
ANCHOR = date(2026, 9, 1)
SINGAPORE = "Asia/Singapore"
UTC = "UTC"

# Tokens that must never appear in the pure dates module's source -- the ORM / DB / wall-clock surface.
_FORBIDDEN_SOURCE_TOKENS = (
    "django.db",
    "django.db.models",
    "upload.models",
    "QuerySet",
    "queryset",
    "filter(",
    "objects.all",
    "connection",
    "rawsql",
    "executemany",
    "CXrStudy",
    "CXrStudy",
    "CXrStudy",
    "get_object_or_create",
    ".save(",
    "bulk_create",
)
# Wall-clock entry points that must never appear -- the "no today / no now fallback" guarantee.
_FORBIDDEN_CLOCK_TOKENS = (
    ".today(",
    ".now(",
    "utcnow",
    "today()",
    "date.today",
    "datetime.now",
    "timezone.now",
    "utcnow",
)


# ---------------------------------------------------------------------------
# Relative windows
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class RelativeWindowTests(SimpleTestCase):
    """Relative tokens resolve against the captured anchor -- never against the wall clock."""

    def test_all_eight_orchestrator_ground_truth_rows_for_tuesday_anchor(self):
        """The eight runbook rows resolve to their exact inclusive ``start..end`` for ``D = 2026-09-01``."""
        expected = {
            "D": (date(2026, 9, 1), date(2026, 9, 1)),
            "D-7": (date(2026, 8, 25), date(2026, 9, 1)),
            "W": (date(2026, 8, 31), date(2026, 9, 1)),
            "W-1": (date(2026, 8, 24), date(2026, 9, 1)),
            "M": (date(2026, 9, 1), date(2026, 9, 1)),
            "M-1": (date(2026, 8, 1), date(2026, 9, 1)),
            "Y": (date(2026, 1, 1), date(2026, 9, 1)),
            "Y-1": (date(2025, 1, 1), date(2026, 9, 1)),
        }
        for token, (start, end) in expected.items():
            with self.subTest(token=token):
                window = resolve_relative_window(token, anchor=ANCHOR, timezone=SINGAPORE)
                self.assertIsInstance(window, ResolvedWindow)
                self.assertEqual(window.start_date, start)
                self.assertEqual(window.end_date, end)
                self.assertFalse(window.explicit)

    def test_relative_windows_are_inclusive_and_always_end_at_anchor(self):
        """Every relative window is inclusive at both ends and its final date is exactly the anchor."""
        for token in ("D", "D-7", "W", "W-1", "M", "M-1", "Y", "Y-1"):
            with self.subTest(token=token):
                window = resolve_relative_window(token, anchor=ANCHOR, timezone=SINGAPORE)
                self.assertEqual(window.end_date, ANCHOR)
                self.assertLessEqual(window.start_date, window.end_date)
                # Inclusive day count is (end - start) + 1, i.e. at least one date.
                self.assertEqual(
                    window.day_count,
                    (window.end_date - window.start_date).days + 1,
                )
                # Inclusive-through-the-anchor coverage means the anchor date itself is inside the range.
                self.assertTrue(window.start_date <= ANCHOR <= window.end_date)

    def test_relative_D_and_D_minus_7_day_windows(self):
        """``D`` is a single date; ``D-7`` spans eight inclusive calendar dates through the anchor."""
        d = resolve_relative_window("D", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((d.start_date, d.end_date), (ANCHOR, ANCHOR))
        self.assertEqual(d.day_count, 1)

        d7 = resolve_relative_window("D-7", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual(d7.start_date, ANCHOR - timedelta(days=7))
        self.assertEqual(d7.start_date, date(2026, 8, 25))
        self.assertEqual(d7.day_count, 8)

    def test_relative_W_week_rules_across_anchor_weekdays(self):
        """``W`` starts on a Monday regardless of the anchor weekday; ``W-1`` is the prior Monday."""
        # Tuesday anchor -> its Monday.
        tuesday = resolve_relative_window("W", anchor=date(2026, 9, 1), timezone=SINGAPORE)
        self.assertEqual(tuesday.start_date, date(2026, 8, 31))
        self.assertEqual(tuesday.start_date.weekday(), 0)

        # Sunday anchor -> still the Monday that began that week.
        sunday = resolve_relative_window("W", anchor=date(2026, 9, 6), timezone=SINGAPORE)
        self.assertEqual(sunday.start_date, date(2026, 8, 31))

        # Monday anchor -> the Monday is the anchor itself.
        monday = resolve_relative_window("W", anchor=date(2026, 8, 31), timezone=SINGAPORE)
        self.assertEqual(monday.start_date, date(2026, 8, 31))
        self.assertEqual(monday.start_date, date(2026, 8, 31))

        # Prior week.
        prior = resolve_relative_window("W-1", anchor=date(2026, 9, 1), timezone=SINGAPORE)
        self.assertEqual(prior.start_date, date(2026, 8, 24))
        self.assertEqual(prior.start_date.weekday(), 0)

    def test_relative_M_and_M_minus_1_month_starts(self):
        """``M`` is the first of the anchor month; ``M-1`` is the first of the prior month."""
        m = resolve_relative_window("M", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((m.start_date, m.end_date), (date(2026, 9, 1), ANCHOR))

        m1 = resolve_relative_window("M-1", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((m1.start_date, m1.end_date), (date(2026, 8, 1), ANCHOR))

        # A January anchor crosses the year boundary correctly.
        jan = resolve_relative_window("M-1", anchor=date(2026, 1, 15), timezone=SINGAPORE)
        self.assertEqual(jan.start_date, date(2025, 12, 1))

    def test_relative_Y_and_Y_minus_1_year_starts(self):
        """``Y`` is the first of January of the anchor year; ``Y-1`` is the prior year's first of January."""
        y = resolve_relative_window("Y", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((y.start_date, y.end_date), (date(2026, 1, 1), ANCHOR))
        y1 = resolve_relative_window("Y-1", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((y1.start_date, y1.end_date), (date(2025, 1, 1), ANCHOR))

    def test_relative_offset_and_token_validation(self):
        """Non-negative offsets extend the rule; a negative / non-integer offset and an unknown token fail typed."""
        # n == 0 gives the base form; larger non-negative offsets extend the same calendar rule.
        self.assertEqual(
            resolve_relative_window("W-0", anchor=ANCHOR, timezone=SINGAPORE).start_date,
            date(2026, 8, 31),
        )
        self.assertEqual(
            resolve_relative_window("M-2", anchor=ANCHOR, timezone=SINGAPORE).start_date,
            date(2026, 7, 1),
        )
        self.assertEqual(
            resolve_relative_window("Y-3", anchor=ANCHOR, timezone=SINGAPORE).start_date,
            date(2023, 1, 1),
        )

        with self.assertRaises(InvalidOffsetError):
            resolve_relative_window("D--3", anchor=ANCHOR, timezone=SINGAPORE)
        with self.assertRaises(InvalidOffsetError):
            resolve_relative_window("D-x", anchor=ANCHOR, timezone=SINGAPORE)
        with self.assertRaises(InvalidWindowError):
            resolve_relative_window("Q", anchor=ANCHOR, timezone=SINGAPORE)

    def test_relative_resolver_raises_missing_anchor_when_handed_none(self):
        """A ``None`` anchor raises :class:`MissingAnchorError` -- there is no wall-clock fallback."""
        with self.assertRaises(MissingAnchorError):
            resolve_relative_window("D", anchor=None, timezone=SINGAPORE)


# ---------------------------------------------------------------------------
# Explicit windows
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ExplicitWindowTests(SimpleTestCase):
    """Explicit ISO overrides stay explicit; only reversed / malformed / mixed inputs are rejected."""

    def test_explicit_iso_window_is_returned_verbatim(self):
        """An explicit ISO start/end pair is returned exactly as requested (the legacy seed range)."""
        window = resolve_window(
            anchor=ANCHOR, timezone=SINGAPORE, start="2025-12-12", end="2026-01-05"
        )
        self.assertTrue(window.explicit)
        self.assertIsNone(window.token)
        self.assertEqual(window.start_date, date(2025, 12, 12))
        self.assertEqual(window.end_date, date(2026, 1, 5))
        self.assertEqual(window.day_count, (date(2026, 1, 5) - date(2025, 12, 12)).days + 1)

    def test_explicit_end_token_D_resolves_to_the_anchor(self):
        """The legacy ``start..D`` seed keeps the explicit start and ends exactly at the anchor."""
        window = resolve_window(anchor=ANCHOR, timezone=SINGAPORE, start="2025-12-12", end="D")
        self.assertEqual(window.start_date, date(2025, 12, 12))
        self.assertEqual(window.end_date, ANCHOR)

    def test_explicit_reversed_range_raises_invalid_window(self):
        """A strictly reversed explicit range (``end < start``) fails with the typed window error."""
        with self.assertRaises(InvalidWindowError):
            resolve_window(anchor=ANCHOR, timezone=SINGAPORE, start="2026-03-10", end="2026-03-01")

    def test_explicit_future_dates_are_never_clamped_to_the_anchor(self):
        """A future explicit range is returned unmodified; the caller reads it as coverage-limited."""
        window = resolve_window(
            anchor=ANCHOR, timezone=SINGAPORE, start="2027-01-05", end="2027-01-09"
        )
        self.assertEqual(window.start_date, date(2027, 1, 5))
        self.assertEqual(window.end_date, date(2027, 1, 9))
        self.assertTrue(window.starts_after_anchor)
        self.assertTrue(window.ends_after_anchor)

    def test_impossible_and_malformed_date_literals_are_rejected(self):
        """An impossible calendar day and a malformed literal both fail via the date constructor path."""
        with self.assertRaises(InvalidDateLiteralError):
            resolve_window(anchor=ANCHOR, timezone=SINGAPORE, start="2026-02-30", end="2026-03-05")
        with self.assertRaises(InvalidDateLiteralError):
            resolve_window(anchor=ANCHOR, timezone=SINGAPORE, start="not-a-date", end="2026-03-05")

    def test_relative_start_with_non_anchor_end_is_rejected(self):
        """The "no mixed relative end other than D" contract rejects a relative start paired with an explicit end."""
        with self.assertRaises(InvalidWindowError):
            resolve_window(anchor=ANCHOR, timezone=SINGAPORE, relative="M", end="2026-09-05")


# ---------------------------------------------------------------------------
# Query boundaries
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class QueryBoundaryTests(SimpleTestCase):
    """Timezone-aware, inclusive query boundaries are produced without importing the ORM."""

    def test_singapore_midnight_boundary_has_plus_eight_offset_and_expected_utc_instant(self):
        """A Singapore local midnight is +08:00 and its UTC instant is eight hours earlier on the wall."""
        window = resolve_relative_window("W", anchor=ANCHOR, timezone=SINGAPORE)  # 2026-08-31 .. 2026-09-01
        boundaries = resolve_query_boundaries(window)
        self.assertIsInstance(boundaries, QueryBoundaries)
        self.assertEqual(boundaries.query_start.utcoffset(), timedelta(hours=8))
        # 2026-08-31 00:00 (+08:00) is the same instant as 2026-08-30 16:00 UTC.
        self.assertEqual(
            boundaries.query_start.astimezone(dt_timezone.utc),
            datetime(2026, 8, 30, 16, 0, 0, tzinfo=dt_timezone.utc),
        )
        # And it equals the directly constructed aware local instant.
        self.assertEqual(
            boundaries.query_start,
            datetime(2026, 8, 31, 0, 0, 0, tzinfo=ZoneInfo(SINGAPORE)),
        )
        # The ISO renderings are exposed for display.
        self.assertEqual(boundaries.query_start_iso, "2026-08-31T00:00:00+08:00")
        self.assertEqual(boundaries.query_end_iso, "2026-09-01T23:59:59.999999+08:00")

    def test_utc_timezone_local_and_utc_walls_agree(self):
        """Under ``UTC`` the local and UTC wall readings coincide and the offset is zero."""
        window = resolve_relative_window("W", anchor=ANCHOR, timezone=UTC)
        boundaries = resolve_query_boundaries(window)
        self.assertEqual(boundaries.query_start.utcoffset(), timedelta(0))
        self.assertEqual(boundaries.query_start.astimezone(dt_timezone.utc), boundaries.query_start)
        self.assertEqual(boundaries.query_start.year, 2026)
        self.assertEqual(boundaries.query_start.month, 8)
        self.assertEqual(boundaries.query_start.day, 31)

    def test_query_boundaries_are_aware_and_ordered(self):
        """Both boundaries carry a real ``tzinfo`` and the lower bound never exceeds the upper."""
        window = resolve_relative_window("Y-1", anchor=ANCHOR, timezone=SINGAPORE)
        boundaries = resolve_query_boundaries(window)
        self.assertIsNotNone(boundaries.query_start.tzinfo)
        self.assertIsNotNone(boundaries.query_end.tzinfo)
        self.assertLessEqual(boundaries.query_start, boundaries.query_end)

    def test_window_span_duration_is_just_under_24_hours_per_day(self):
        """An N-day inclusive window spans exactly ``N`` days minus one microsecond."""
        window = resolve_relative_window("D-7", anchor=ANCHOR, timezone=SINGAPORE)  # 8 dates
        boundaries = resolve_query_boundaries(window)
        self.assertEqual(window.day_count, 8)
        self.assertEqual(
            boundaries.instant_span,
            timedelta(days=8, microseconds=-1),
        )
        self.assertLess(boundaries.instant_span, timedelta(days=8))
        self.assertGreaterEqual(boundaries.instant_span, timedelta(days=7))

    def test_every_interior_date_localises_within_the_inclusive_bounds(self):
        """Any date inside the window localises between the two bounds; a date before the start does not."""
        window = resolve_relative_window("W-1", anchor=ANCHOR, timezone=SINGAPORE)  # 2026-08-24 .. 2026-09-01
        boundaries = resolve_query_boundaries(window)
        cursor = window.start_date
        while cursor <= window.end_date:
            with self.subTest(date=cursor.isoformat()):
                mid = localise_day_start(cursor, timezone=SINGAPORE)
                late = localise_day_end(cursor, timezone=SINGAPORE)
                self.assertLessEqual(boundaries.query_start, mid)
                self.assertLessEqual(mid, boundaries.query_end)
                self.assertLessEqual(late, boundaries.query_end)
            cursor = cursor + timedelta(days=1)
        # The day before the window begins is entirely outside the lower bound.
        before = localise_day_end(window.start_date - timedelta(days=1), timezone=SINGAPORE)
        self.assertLess(before, boundaries.query_start)


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class BucketingTests(SimpleTestCase):
    """Buckets follow only the span and size, are labelled, and flag clipped boundary periods as partial."""

    def test_day_buckets_yield_one_bucket_per_date(self):
        """Day bucketing emits one non-partial bucket per calendar date across the span."""
        buckets = bucket_range(
            start_date=date(2026, 8, 31), end_date=date(2026, 9, 2), size="day"
        )
        self.assertEqual([b.start_date for b in buckets], [date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2)])
        self.assertEqual([b.index for b in buckets], [0, 1, 2])
        self.assertTrue(all(b.size == "day" for b in buckets))
        self.assertTrue(all(b.partial is False for b in buckets))
        self.assertEqual(buckets[0].label, "2026-08-31/2026-08-31")

    def test_week_buckets_are_monday_start_periods(self):
        """Week bucketing emits Monday-start periods with the natural period boundaries and a stable label."""
        buckets = bucket_range(
            start_date=date(2026, 8, 31), end_date=date(2026, 9, 6), size="week"
        )
        self.assertEqual(len(buckets), 1)
        week = buckets[0]
        self.assertIsInstance(week, Bucket)
        self.assertEqual(week.period_start, date(2026, 8, 31))
        self.assertEqual(week.period_end, date(2026, 9, 6))
        self.assertEqual(week.period_start.weekday(), 0)
        self.assertEqual(week.label, "2026-08-31/2026-09-06")

    def test_week_bucket_is_partial_when_the_span_clips_the_week(self):
        """A Monday..Thursday span produces a single week bucket flagged partial (its natural week is cut)."""
        buckets = bucket_range(
            start_date=date(2026, 8, 31), end_date=date(2026, 9, 3), size="week"
        )
        self.assertEqual(len(buckets), 1)
        week = buckets[0]
        self.assertTrue(week.partial)
        self.assertEqual(week.period_start, date(2026, 8, 31))
        self.assertEqual(week.period_end, date(2026, 9, 6))
        # The clipped coverage stays inside the requested span.
        self.assertEqual(week.start_date, date(2026, 8, 31))
        self.assertEqual(week.end_date, date(2026, 9, 3))

    def test_full_interior_week_is_not_partial(self):
        """A week fully inside a longer span is not partial even when a neighbouring week is clipped."""
        # Fri 2026-08-28 .. Sun 2026-09-06 clips the first week but leaves the second whole.
        buckets = bucket_range(
            start_date=date(2026, 8, 28), end_date=date(2026, 9, 6), size="week"
        )
        self.assertEqual(len(buckets), 2)
        self.assertTrue(buckets[0].partial)   # 2026-08-24/.. week clipped on the left edge
        self.assertFalse(buckets[1].partial)  # 2026-08-31/2026-09-06 week sits fully inside the span

    def test_month_buckets_label_partial_boundaries(self):
        """Month bucketing yields calendar months; edge months clipped by the span are partial, an interior month is not."""
        buckets = bucket_range(
            start_date=date(2026, 1, 5), end_date=date(2026, 3, 20), size="month"
        )
        self.assertEqual([b.label for b in buckets], [
            "2026-01-01/2026-01-31",
            "2026-02-01/2026-02-28",
            "2026-03-01/2026-03-31",
        ])
        self.assertEqual([b.partial for b in buckets], [True, False, True])

    def test_year_buckets_label_partial_boundaries(self):
        """Year bucketing yields calendar years with Jan-1..Dec-31 periods, clipped edges flagged partial."""
        buckets = bucket_range(
            start_date=date(2025, 7, 1), end_date=date(2026, 6, 30), size="year"
        )
        self.assertEqual([b.label for b in buckets], [
            "2025-01-01/2025-12-31",
            "2026-01-01/2026-12-31",
        ])
        self.assertEqual([b.partial for b in buckets], [True, True])
        # A single whole year inside a wider span is not partial.
        whole = bucket_range(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), size="year")
        self.assertEqual([b.partial for b in whole], [False])

    def test_bucketing_is_independent_of_the_resolved_relative_window(self):
        """Bucketing is driven only by the span, not the resolved window nor the anchor."""
        # The relative window for the anchor spans 2026-08-31..2026-09-01 (the W week).
        window = resolve_relative_window("W", anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual((window.start_date, window.end_date), (date(2026, 8, 31), date(2026, 9, 1)))

        # Bucket a completely different span; the buckets follow the span, not the window.
        other = bucket_range(
            start_date=date(2024, 3, 4), end_date=date(2024, 3, 8), size="week"
        )
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0].period_start, date(2024, 3, 4))  # 2024-03-04 is a Monday
        self.assertEqual(other[0].period_start.weekday(), 0)
        self.assertEqual(other[0].period_end, date(2024, 3, 10))
        self.assertEqual(other[0].label, "2024-03-04/2024-03-10")
        # The buckets do not coincide with the anchor window boundaries at all.
        self.assertNotEqual(other[0].period_start, window.start_date)

    def test_unknown_bucket_size_raises_typed_error(self):
        """A bucket size outside day/week/month/year is rejected with the typed bucket error."""
        with self.assertRaises(UnknownBucketError):
            bucket_range(start_date=ANCHOR, end_date=ANCHOR, size="quarter")
        with self.assertRaises(InvalidWindowError):
            bucket_range(start_date=date(2026, 9, 5), end_date=date(2026, 9, 1), size="day")


# ---------------------------------------------------------------------------
# Anchor provenance / cannot move the anchor
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class AnchorProvenanceTests(SimpleTestCase):
    """The anchor is server-captured: readers can not submit, move or advance it."""

    def test_capture_anchor_takes_latest_complete_eligible_date(self):
        """``capture_anchor`` derives ``D`` from the latest complete, eligible candidate (not from "now")."""
        candidates = [
            date(2026, 8, 28),
            date(2026, 9, 1),   # latest complete
            date(2026, 8, 20),
        ]
        captured = capture_anchor(candidates, timezone=SINGAPORE, provenance="widget-a")
        self.assertIsInstance(captured, Anchor)
        self.assertEqual(captured.date, date(2026, 9, 1))
        self.assertEqual(captured.timezone, SINGAPORE)
        self.assertEqual(captured.provenance, "widget-a")

    def test_capture_anchor_returns_none_when_empty_or_nothing_complete(self):
        """An empty set -- or one where nothing is complete/eligible -- yields ``None``, never a fabricated date."""
        self.assertIsNone(capture_anchor([]))
        self.assertIsNone(
            capture_anchor(
                [
                    {"event_date": date(2026, 9, 1), "complete": False, "eligible": True},
                    {"event_date": date(2026, 8, 28), "complete": True, "eligible": False},
                ],
                timezone=SINGAPORE,
            )
        )

    def test_capture_anchor_ignores_a_newer_incomplete_row(self):
        """A newer row whose required fields are incomplete cannot advance ``D``."""
        candidates = [
            {"event_date": date(2026, 9, 1), "complete": True, "eligible": True},
            {"event_date": date(2026, 8, 28), "complete": True, "eligible": True},
            {"event_date": date(2026, 9, 10), "complete": False, "eligible": True},  # newer but incomplete
        ]
        captured = capture_anchor(candidates, timezone=SINGAPORE)
        self.assertEqual(captured.date, date(2026, 9, 1))

    def test_user_submitted_anchor_field_is_ignored(self):
        """A reader-submitted ``anchor``/``D``/``as_of`` field cannot change the captured anchor."""
        request = {"relative": "D", "anchor": "2026-08-28", "as_of": "2026-08-28", "D": "2026-08-28"}
        resolved = resolve_request(request, captured_anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual(resolved.start_date, date(2026, 9, 1))
        self.assertEqual(resolved.end_date, date(2026, 9, 1))

    def test_subgroup_narrowing_does_not_move_the_anchor_but_reports_coverage(self):
        """Narrowing to the older subgroup keeps W-1 at 2026-08-24..2026-09-01 and reports coverage separately."""
        request = {
            "relative": "W-1",
            "subgroup_latest_eligible_date": "2026-08-28",
        }
        resolved = resolve_request(request, captured_anchor=ANCHOR, timezone=SINGAPORE)
        self.assertEqual(resolved.start_date, date(2026, 8, 24))
        self.assertEqual(resolved.end_date, date(2026, 9, 1))  # the anchor did not move
        self.assertEqual(resolved.subgroup_latest_eligible_date, date(2026, 8, 28))
        self.assertIn("2026-08-24", resolved.coverage_note)
        self.assertIn("2026-09-01", resolved.coverage_note)
        self.assertIn("2026-08-28", resolved.coverage_note)

    def test_reader_cannot_advance_the_anchor_with_a_newer_incomplete_row(self):
        """Even a request that submits a later anchor / subgroup leaves the resolved window pinned to ``D``."""
        request = {
            "relative": "W-1",
            "anchor": "2026-09-10",
            "as_of": "2026-09-10",
            "subgroup_latest_eligible_date": "2026-09-10",
        }
        resolved = resolve_request(request, captured_anchor=Anchor(date=ANCHOR, timezone=SINGAPORE))
        self.assertEqual(resolved.end_date, date(2026, 9, 1))
        self.assertEqual(resolved.start_date, date(2026, 8, 24))
        self.assertFalse(resolved.ends_after_anchor)

    def test_resolvers_raise_missing_anchor_when_handed_none(self):
        """Both resolvers raise :class:`MissingAnchorError` for a ``None`` anchor -- no "today" is invented."""
        with self.assertRaises(MissingAnchorError):
            resolve_window(anchor=None, timezone=SINGAPORE, relative="W-1")
        with self.assertRaises(MissingAnchorError):
            resolve_request({"relative": "D"}, captured_anchor=None, timezone=SINGAPORE)


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class PurityTests(SimpleTestCase):
    """The module is ORM-free and never reads the wall clock -- enforced structurally and by source scan."""

    def setUp(self):
        self.source = inspect.getsource(dates_module)

    def test_module_source_contains_no_orm_or_database_tokens(self):
        """No ORM / DB surface token appears anywhere in the pure module's source."""
        for token in _FORBIDDEN_SOURCE_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token, self.source)

    def test_module_source_never_reads_the_wall_clock(self):
        """No ``today`` / ``now`` / ``utcnow`` call syntax appears -- the no-today-fallback guarantee."""
        for token in _FORBIDDEN_CLOCK_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token, self.source)

    def test_module_globals_expose_only_stdlib_dependencies(self):
        """The module imported nothing from Django / the ORM -- only standard-library modules are bound."""
        namespace = vars(dates_module)
        for forbidden in ("django", "upload", "models", "CXrStudy", "connection", "rawsql"):
            self.assertNotIn(forbidden, namespace)
        # Every imported module object comes from the standard library, never from django.* / upload.*.
        for name, value in namespace.items():
            if not isinstance(value, types.ModuleType):
                continue
            module_name = getattr(value, "__name__", "")
            self.assertFalse(
                module_name == "django" or module_name.startswith("django."),
                f"{name} unexpectedly imports {module_name}",
            )
            self.assertFalse(
                module_name == "upload" or module_name.startswith("upload."),
                f"{name} unexpectedly imports {module_name}",
            )
        # The expected stdlib collaborators are bound, confirming the framework-free design.
        self.assertIn("ZoneInfo", namespace)
        self.assertIn("date", namespace)
        self.assertIn("timedelta", namespace)
        self.assertIn("dataclass", namespace)
