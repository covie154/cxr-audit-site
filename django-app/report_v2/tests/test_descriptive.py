# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused, database-free coverage for the report-v2 descriptive measurement layer.

These exercise the pure counting and duration entry points in
:mod:`report_v2.measurements.descriptive`: row counts, label-vocabulary counts, free
categorical counts and the single documented-quantile duration summary. The whole suite is
pinned against the runbook's Tukey hand-check and the descriptive task's guarantees:

* the documented quantile convention is ONE module-wide choice (the lower order statistic,
  ``Q(p) = sorted[floor(p * (n - 1))]``) honoured identically by ``q1``/``median``/``q3`` and
  by the two tail summaries ``p5``/``p95`` -- one convention, never a per-call-site variant;
* the named hand-check reproduces exactly: ``[1..10, 100]`` gives ``Q1=3``, ``median=6``,
  ``Q3=8``, ``IQR=5``, an upper fence of ``15.5``, the **only** outlier ``100`` and an
  **upper whisker of ``10``** -- a *whisker is an observed datum*, never the fence value;
* outliers are *reported, never dropped*: they still move ``n``, ``min``/``max`` and the mean;
* ``p5`` and ``p95`` are SEPARATE tail summaries with their own method note: they are not the
  box whiskers and are not folded into ``q1``/``q3``;
* missing / invalid durations (``None``, ``bool``, non-numeric, non-finite, negative) are
  EXCLUDED and COUNTED in ``excluded_missing`` / ``excluded_invalid`` -- never read as ``0``;
* the declared ``n == 1`` behaviour is asserted, not assumed, and an empty population returns
  an all-``None`` summary with a note instead of raising or fabricating zeroes.

No database, ORM, real/clinical data or the reference snapshot are touched: the whole suite is
:class:`django.test.SimpleTestCase`, the populations are plain synthetic value lists plus the
synthetic in-memory ``factories`` (``timing_fixture``), and PRIME is read only through the frozen
catalog. The production static / SSL / mail configuration is overridden away so the suite is
hermetic.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import math
import re

from django.test import SimpleTestCase, override_settings

from report_v2.measurements import descriptive as descriptive_module
from report_v2.measurements.descriptive import (
    QUANTILE_METHOD,
    TAIL_METHOD,
    DescriptiveError,
    DurationSummary,
    UnexpectedQuantileMethod,
    categorical_count,
    duration_summary,
    label_count,
    record_count,
)
from report_v2.tests.factories import (
    INVALID_DURATION_SENTINEL,
    RESERVED_ACCESSION_BASE,
    RESERVED_ACCESSION_SPAN,
    SYNTH_MARK,
    TIMING_REFERENCE_SECONDS,
    timing_fixture,
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# The runbook Tukey block: the eleven observed durations of the named hand-check.
_TUKEY_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100]


def _reference_quantile(values, p):
    """Independent restatement of the documented convention, for cross-checking the module."""
    ordered = sorted(values)
    n = len(ordered)
    index = math.floor(p * (n - 1))
    index = max(0, min(n - 1, index))
    return ordered[index]


# ---------------------------------------------------------------------------
# A. Row / label / categorical counting.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class CountingTests(SimpleTestCase):
    """``record_count`` / ``label_count`` / ``categorical_count`` are plain tallies."""

    def test_record_count_counts_present_mapping_like_rows(self):
        rows = [{}, None, {"a": 1}, "x", 5]
        # Only the two mapping-like rows are eligible; None / str / int are not.
        self.assertEqual(record_count(rows), 2)

    def test_record_count_counts_a_row_that_does_not_opt_out(self):
        self.assertEqual(record_count([{}, {}]), 2)

    def test_record_count_is_zero_for_an_empty_population(self):
        self.assertEqual(record_count([]), 0)

    def test_label_count_restricts_to_the_declared_vocabulary(self):
        rows = [{"l": "a"}, {"l": "a"}, {"l": "b"}, {"l": "off"}, {"l": None}]
        counts = label_count(rows, label_key="l", vocabulary=("a", "b", "z"))
        # Every declared label is present and seeded to 0; off-vocabulary values never appear.
        self.assertEqual(counts, {"a": 2, "b": 1, "z": 0})

    def test_label_count_reconciles_against_the_supplied_rows(self):
        rows = [{"l": "a"}, {"l": "b"}, {"l": "off"}, {"l": None}]
        counts = label_count(rows, label_key="l", vocabulary=("a", "b"))
        tallied = sum(counts.values())
        off_vocabulary = sum(1 for r in rows if r["l"] is not None and r["l"] not in ("a", "b"))
        missing = sum(1 for r in rows if r["l"] is None)
        self.assertEqual(tallied + off_vocabulary + missing, len(rows))
        self.assertEqual(tallied, 2)

    def test_label_count_without_a_vocabulary_tallies_every_observed_value(self):
        rows = [{"l": "a"}, {"l": "a"}, {"l": "x"}, {"l": None}]
        self.assertEqual(label_count(rows, label_key="l"), {"a": 2, "x": 1})

    def test_label_count_seeds_zero_when_a_column_is_entirely_absent(self):
        # A missing column key is a missing value everywhere: the vocabulary still appears at 0.
        self.assertEqual(label_count([{"other": 1}], label_key="l", vocabulary=(1, 0)), {1: 0, 0: 0})

    def test_label_count_skips_non_mapping_rows(self):
        self.assertEqual(label_count([None, {"l": 1}], label_key="l", vocabulary=(1, 0)), {1: 1, 0: 0})

    def test_categorical_count_tallies_observed_values_and_skips_missing(self):
        rows = [{"c": "a"}, {"c": "a"}, {"c": "b"}, {"c": None}]
        self.assertEqual(categorical_count(rows, column="c"), {"a": 2, "b": 1})

    def test_categorical_count_keeps_falsy_but_real_categories(self):
        # ``""`` and ``0`` are genuine categories; only ``None`` is treated as missing.
        self.assertEqual(categorical_count([{"c": ""}, {"c": 0}, {"c": 0}], column="c"), {"": 1, 0: 2})

    def test_categorical_count_over_the_synthetic_site_column(self):
        rows = timing_fixture()
        counts = categorical_count(rows, column="site")
        self.assertEqual(sum(counts.values()), len(rows))
        self.assertNotIn(None, counts)


# ---------------------------------------------------------------------------
# B. The named Tukey hand-check (must hold exactly).
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class TukeyHandCheckTests(SimpleTestCase):
    """The runbook block: only ``100`` is an outlier and the upper whisker is ``10``."""

    def setUp(self):
        self.summary = duration_summary(_TUKEY_VALUES)

    def test_documented_hand_check_upper_whisker_and_single_outlier(self):
        s = self.summary
        self.assertEqual(s.n, 11)
        self.assertEqual(s.q1, 3)
        self.assertEqual(s.median, 6)
        self.assertEqual(s.q3, 8)
        self.assertEqual(s.iqr, 5)
        self.assertEqual(s.lower_fence, -4.5)
        self.assertEqual(s.upper_fence, 15.5)
        # The ONLY outlier is 100 ...
        self.assertEqual(s.outliers, [100])
        # ... and the UPPER whisker is the largest observed value <= 15.5, i.e. 10.
        self.assertEqual(s.upper_whisker, 10)
        self.assertEqual(s.lower_whisker, 1)

    def test_upper_whisker_is_an_observed_value_not_the_fence(self):
        s = self.summary
        self.assertEqual(s.upper_whisker, 10)
        self.assertNotEqual(s.upper_whisker, s.upper_fence)
        # A whisker must be a datum actually present in the population, not a computed cut.
        self.assertIn(s.upper_whisker, _TUKEY_VALUES)
        self.assertIn(s.lower_whisker, _TUKEY_VALUES)

    def test_outlier_is_reported_not_dropped(self):
        s = self.summary
        # Outliers stay in the aggregate: n / min / max / mean all still see the 100.
        self.assertEqual(s.n, 11)
        self.assertEqual(s.min, 1)
        self.assertEqual(s.max, 100)
        self.assertEqual(s.excluded_missing, 0)
        self.assertEqual(s.excluded_invalid, 0)
        self.assertAlmostEqual(s.mean, 155 / 11)

    def test_outliers_field_is_a_fresh_container_not_an_input_alias(self):
        values = list(_TUKEY_VALUES)
        s = duration_summary(values)
        self.assertIsNot(s.outliers, values)
        self.assertEqual(values, _TUKEY_VALUES)  # the caller's list is never mutated

    def test_hand_check_is_order_insensitive(self):
        shuffled = [10, 1, 100, 5, 9, 2, 8, 3, 7, 4, 6]
        other = duration_summary(shuffled)
        for field in ("n", "min", "max", "mean", "q1", "median", "q3", "iqr",
                     "lower_whisker", "upper_whisker", "p5", "p95"):
            self.assertEqual(getattr(other, field), getattr(self.summary, field), field)
        self.assertEqual(other.outliers, [100])

    def test_no_outliers_when_everything_sits_inside_the_fences(self):
        s = duration_summary([10, 11, 12, 13, 14])
        self.assertEqual(s.outliers, [])
        self.assertEqual(s.lower_whisker, 10)
        self.assertEqual(s.upper_whisker, 14)


# ---------------------------------------------------------------------------
# C. The single quantile convention.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class QuantileConventionTests(SimpleTestCase):
    """One documented convention, used identically at every call site."""

    def test_module_declares_exactly_one_quantile_method_constant(self):
        self.assertIsInstance(QUANTILE_METHOD, str)
        self.assertTrue(QUANTILE_METHOD.strip())
        named = {
            name: value for name, value in vars(descriptive_module).items()
            if name.isupper() and "QUANTILE" in name and isinstance(value, str)
        }
        self.assertEqual(list(named), ["QUANTILE_METHOD"], named)

    def test_documented_convention_is_the_lower_order_statistic(self):
        # Q(p) = sorted[floor(p * (n - 1))]; no interpolation between two observations.
        s = duration_summary([1, 2, 3, 4])
        self.assertEqual(s.q1, 1)
        self.assertEqual(s.median, 2)
        self.assertEqual(s.q3, 3)
        # An *exclusive* / interpolated method would answer 1.75 / 2.5 / 3.25 here.
        self.assertNotEqual(s.q1, 1.75)
        self.assertNotEqual(s.median, 2.5)
        self.assertNotEqual(s.q3, 3.25)

    def test_every_quantile_field_matches_the_independent_restatement(self):
        for values in (
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100],
            list(range(1, 101)),
            [210.0, 210.0, 210.0],
            [7.5, 3.25, 9.0, 0.5],
            [42],
        ):
            s = duration_summary(values)
            pairs = ((0.25, s.q1), (0.50, s.median), (0.75, s.q3), (0.05, s.p5), (0.95, s.p95))
            for fraction, got in pairs:
                self.assertEqual(got, _reference_quantile(values, fraction),
                                 f"fraction {fraction} for {values}")

    def test_iqr_and_fences_follow_from_the_same_quartiles(self):
        for values in ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100], [3, 1, 2, 9, 7, 5]):
            s = duration_summary(values)
            self.assertEqual(s.iqr, s.q3 - s.q1)
            self.assertEqual(s.lower_fence, s.q1 - 1.5 * s.iqr)
            self.assertEqual(s.upper_fence, s.q3 + 1.5 * s.iqr)

    def test_quartiles_and_tail_percentiles_share_one_method_string(self):
        s = duration_summary([1, 2, 3])
        self.assertEqual(s.quantile_method, QUANTILE_METHOD)
        self.assertEqual(s.tail_method, TAIL_METHOD)
        self.assertIn(QUANTILE_METHOD, s.note + s.tail_method + s.quantile_method)

    def test_a_differently_documented_method_is_rejected_not_silently_used(self):
        # The convention cannot drift: a caller naming another method is refused with a typed error.
        with self.assertRaises(UnexpectedQuantileMethod):
            duration_summary([1, 2, 3], documented_quantile_method="linear interpolation")
        with self.assertRaises(DescriptiveError):  # the typed base also catches it
            duration_summary([1, 2, 3], documented_quantile_method="exclusive")

    def test_default_documented_method_is_the_module_constant(self):
        signature = inspect.signature(duration_summary)
        self.assertEqual(
            signature.parameters["documented_quantile_method"].default, QUANTILE_METHOD
        )


# ---------------------------------------------------------------------------
# D. P5 / P95 are SEPARATE summaries.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class TailPercentileTests(SimpleTestCase):
    """``p5``/``p95`` are their own tail summaries -- not the whiskers, not the quartiles."""

    def test_p95_is_not_the_upper_whisker_and_not_q3(self):
        # High-side outliers: the whisker stops at the fence while p95 keeps reaching into the tail.
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 200, 300, 400, 500]
        s = duration_summary(values)
        self.assertEqual(s.upper_whisker, 200)   # largest observed <= the 244.0 fence
        self.assertEqual(s.p95, 400)
        self.assertNotEqual(s.p95, s.upper_whisker)
        self.assertNotEqual(s.p95, s.q3)

    def test_p5_is_not_the_lower_whisker_and_not_q1(self):
        # Low-side outlier: the whisker starts at the first datum inside the lower fence (10)
        # while p5 reaches the extreme low value (0), which is itself reported as an outlier.
        values = [0, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 100]
        s = duration_summary(values)
        self.assertEqual(s.lower_fence, 2.0)
        self.assertEqual(s.lower_whisker, 10)
        self.assertEqual(s.p5, 0)
        self.assertEqual(s.q1, 11)
        self.assertLess(s.p5, s.lower_whisker)
        self.assertNotEqual(s.p5, s.q1)
        self.assertIn(0, s.outliers)

    def test_tail_summaries_are_ordered_inside_the_extremes(self):
        s = duration_summary(list(range(1, 101)))
        self.assertLessEqual(s.min, s.p5)
        self.assertLessEqual(s.p5, s.q1)
        self.assertLessEqual(s.q3, s.p95)
        self.assertLessEqual(s.p95, s.max)

    def test_tail_summaries_carry_their_own_method_note(self):
        s = duration_summary(list(range(1, 21)))
        self.assertIn("p5", s.tail_method)
        self.assertIn("p95", s.tail_method)
        self.assertIn("separate", s.note)   # the note names the separation, and does not call p5/p95 whiskers
        self.assertNotIn("p5", s.note.replace("p5/p95", ""))

    def test_tail_percentiles_never_drop_the_outlier_from_the_aggregate(self):
        s = duration_summary([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100])
        self.assertEqual(s.n, 11)
        self.assertEqual(s.p95, 10)          # the 95th percentile is an interior datum
        self.assertEqual(s.max, 100)         # ... while the outlier is still in the population
        self.assertEqual(s.outliers, [100])


# ---------------------------------------------------------------------------
# E. Missing / invalid exclusion, counted not zeroed.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ExclusionTests(SimpleTestCase):
    """Invalid durations are excluded AND counted, never coerced to ``0``."""

    def test_none_and_negative_and_nonnumeric_excluded_and_counted(self):
        values = [10, 20, 30, None, -1, "300", True, float("nan"), float("inf"), 40]
        s = duration_summary(values)
        self.assertEqual(s.n, 4)                       # 10, 20, 30, 40
        self.assertEqual(s.excluded_missing, 1)         # the single None
        self.assertEqual(s.excluded_invalid, 5)         # -1, "300", True, nan, inf
        self.assertEqual(s.n + s.excluded_missing + s.excluded_invalid, len(values))

    def test_a_bool_is_never_read_as_a_duration(self):
        # ``True`` is an ``int`` subclass; as a flag it is invalid, and it is not a 1 either.
        s = duration_summary([True, False, 5])
        self.assertEqual(s.n, 1)
        self.assertEqual(s.excluded_invalid, 2)
        self.assertEqual(s.min, 5)
        self.assertEqual(s.max, 5)

    def test_zero_is_a_valid_duration(self):
        s = duration_summary([0, 0, 10])
        self.assertEqual(s.n, 3)
        self.assertEqual(s.excluded_missing, 0)
        self.assertEqual(s.excluded_invalid, 0)
        self.assertEqual(s.min, 0)
        self.assertAlmostEqual(s.mean, 10 / 3)

    def test_negative_sentinel_is_invalid_not_a_large_magnitude(self):
        s = duration_summary([100.0, INVALID_DURATION_SENTINEL])
        self.assertEqual(s.n, 1)
        self.assertEqual(s.excluded_invalid, 1)
        self.assertEqual(s.min, 100.0)
        self.assertEqual(s.max, 100.0)

    def test_all_invalid_input_is_empty_never_zero_filled(self):
        s = duration_summary([None, None, -5, "x"])
        self.assertEqual(s.n, 0)
        self.assertEqual(s.excluded_missing, 2)
        self.assertEqual(s.excluded_invalid, 2)
        # An empty summary is empty -- every number is None, and nothing was counted as a real 0.
        for field in ("min", "max", "mean", "q1", "median", "q3", "iqr",
                     "lower_fence", "upper_fence", "lower_whisker", "upper_whisker",
                     "p5", "p95"):
            self.assertIsNone(getattr(s, field), field)
        self.assertEqual(s.outliers, [])

    def test_empty_population_returns_a_note_instead_of_raising(self):
        s = duration_summary([])
        self.assertEqual(s.n, 0)
        self.assertEqual(s.excluded_missing, 0)
        self.assertEqual(s.excluded_invalid, 0)
        self.assertTrue(s.note.strip())
        self.assertIsNone(s.mean)

    def test_exclusion_counts_are_never_none(self):
        for values in ([], [1], [None, "x"], [1, 2, 3]):
            s = duration_summary(values)
            self.assertIsInstance(s.excluded_missing, int)
            self.assertIsInstance(s.excluded_invalid, int)
            self.assertNotIsInstance(s.excluded_missing, bool)
            self.assertNotIsInstance(s.excluded_invalid, bool)


# ---------------------------------------------------------------------------
# F. Declared single-value behaviour (n == 1).
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class SingleValueTests(SimpleTestCase):
    """The declared ``n == 1`` behaviour is asserted: every quantile and whisker is ``v``."""

    def test_single_value_collapses_to_that_value(self):
        s = duration_summary([42])
        self.assertEqual(s.n, 1)
        self.assertEqual(s.min, 42)
        self.assertEqual(s.max, 42)
        self.assertEqual(s.mean, 42)
        self.assertEqual(s.q1, 42)
        self.assertEqual(s.median, 42)
        self.assertEqual(s.q3, 42)
        self.assertEqual(s.iqr, 0)
        self.assertEqual(s.lower_fence, 42)
        self.assertEqual(s.upper_fence, 42)
        self.assertEqual(s.lower_whisker, 42)
        self.assertEqual(s.upper_whisker, 42)
        self.assertEqual(s.p5, 42)
        self.assertEqual(s.p95, 42)
        self.assertEqual(s.outliers, [])

    def test_single_value_note_declares_the_collapse(self):
        self.assertIn("single observation", duration_summary([42]).note)

    def test_a_single_valid_value_among_junk_still_collapses(self):
        s = duration_summary([None, "nope", 7, -1])
        self.assertEqual(s.n, 1)
        self.assertEqual(s.q1, 7)
        self.assertEqual(s.median, 7)
        self.assertEqual(s.q3, 7)
        self.assertEqual(s.lower_whisker, 7)
        self.assertEqual(s.upper_whisker, 7)
        self.assertIn("single observation", s.note)

    def test_all_equal_values_have_zero_iqr_and_no_outliers(self):
        s = duration_summary([7, 7, 7, 7])
        self.assertEqual(s.iqr, 0)
        self.assertEqual(s.lower_fence, 7)
        self.assertEqual(s.upper_fence, 7)
        self.assertEqual(s.outliers, [])
        self.assertEqual(s.lower_whisker, 7)
        self.assertEqual(s.upper_whisker, 7)


# ---------------------------------------------------------------------------
# G. The synthetic timing fixture drives the summary end to end.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class TimingFixtureDurationTests(SimpleTestCase):
    """``timing_fixture`` rows stay synthetic and reconcile through ``duration_summary``."""

    def setUp(self):
        self.rows = timing_fixture()
        self.values = [row["duration_seconds"] for row in self.rows]
        self.summary = duration_summary(self.values)

    def test_fixture_rows_stay_inside_the_reserved_synthetic_block(self):
        for row in self.rows:
            self.assertGreaterEqual(row["accession"], RESERVED_ACCESSION_BASE)
            self.assertLess(row["accession"], RESERVED_ACCESSION_BASE + RESERVED_ACCESSION_SPAN)

    def test_fixture_excludes_the_missing_and_invalid_rows_and_counts_them(self):
        missing = sum(1 for r in self.rows if r["duration_seconds"] is None)
        invalid = sum(
            1 for r in self.rows
            if isinstance(r["duration_seconds"], (int, float))
            and not isinstance(r["duration_seconds"], bool)
            and r["duration_seconds"] < 0
        )
        self.assertEqual(missing, 1)
        self.assertEqual(invalid, 1)
        self.assertEqual(self.summary.excluded_missing, missing)
        self.assertEqual(self.summary.excluded_invalid, invalid)
        self.assertEqual(
            self.summary.n + self.summary.excluded_missing + self.summary.excluded_invalid,
            len(self.rows),
        )

    def test_fixture_outlier_is_reported_and_kept_in_the_aggregate(self):
        self.assertEqual(INVALID_DURATION_SENTINEL, -1.0)
        self.assertIn(61000.0, self.summary.outliers)
        self.assertEqual(self.summary.max, 61000.0)
        self.assertEqual(self.summary.n, len(self.values) - 2)

    def test_fixture_whiskers_bracket_the_non_outlier_mass(self):
        s = self.summary
        self.assertLess(s.lower_whisker, s.upper_whisker)
        self.assertLessEqual(s.lower_whisker, s.q1)
        self.assertGreaterEqual(s.upper_whisker, s.q3)
        for datum in self.values:
            if datum is None or datum < 0:
                continue
            if datum < s.lower_fence or datum > s.upper_fence:
                self.assertIn(datum, s.outliers)
            else:
                self.assertNotIn(datum, s.outliers)

    def test_fixture_reference_value_is_in_the_measured_population(self):
        self.assertIn(TIMING_REFERENCE_SECONDS, self.values)
        self.assertLessEqual(self.summary.min, TIMING_REFERENCE_SECONDS)
        self.assertGreaterEqual(self.summary.max, TIMING_REFERENCE_SECONDS)

    def test_single_value_group_from_the_fixture_collapses(self):
        singles = [r["duration_seconds"] for r in self.rows if r["missing_field"] == "single_value"]
        self.assertEqual(len(singles), 3)
        s = duration_summary(singles)
        self.assertEqual(s.q1, 210.0)
        self.assertEqual(s.median, 210.0)
        self.assertEqual(s.q3, 210.0)
        self.assertEqual(s.iqr, 0)
        self.assertEqual(s.outliers, [])


# ---------------------------------------------------------------------------
# H. Purity / shape guards.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class PurityTests(SimpleTestCase):
    """The module is a pure value layer: a frozen dataclass, stdlib only, no ORM."""

    def test_duration_summary_is_a_frozen_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(DurationSummary))
        self.assertTrue(DurationSummary.__dataclass_params__.frozen)
        s = duration_summary([1, 2, 3])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.n = 99

    def test_documented_field_surface_is_present(self):
        declared = {f.name for f in dataclasses.fields(DurationSummary)}
        for field in ("n", "min", "max", "mean", "q1", "median", "q3", "iqr",
                     "lower_whisker", "upper_whisker", "outliers", "p5", "p95",
                     "excluded_missing", "excluded_invalid", "quantile_method", "note"):
            self.assertIn(field, declared)

    def test_summary_serialises_with_the_stdlib_dataclass_helper(self):
        snap = dataclasses.asdict(duration_summary(_TUKEY_VALUES))
        self.assertIsInstance(snap, dict)
        self.assertEqual(snap["upper_whisker"], 10)
        self.assertEqual(snap["outliers"], [100])
        json.dumps(snap)   # JSON-safe for the snapshot layer

    def test_module_imports_no_orm_db_or_network_layer(self):
        with open(descriptive_module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        imported = re.findall(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)", source, re.MULTILINE)
        roots = {name.split(".")[0] for name in imported}
        for forbidden in ("django", "upload", "models", "sqlite3", "requests", "urllib"):
            self.assertNotIn(forbidden, roots)
        self.assertIn("dataclasses", roots)
        self.assertIn("math", roots)

    def test_entry_points_take_values_and_return_values(self):
        self.assertIsInstance(duration_summary([1, 2, 3]), DurationSummary)
        self.assertIsInstance(record_count([{}]), int)
        self.assertIsInstance(label_count([{"l": 1}], label_key="l", vocabulary=(1,)), dict)
        self.assertIsInstance(categorical_count([{"c": "a"}], column="c"), dict)

    def test_helpers_do_not_mutate_their_input(self):
        values = list(_TUKEY_VALUES)
        snapshot = list(values)
        duration_summary(values)
        self.assertEqual(values, snapshot)
        rows = [{"l": 1}, {"l": 0}]
        row_snapshot = [{"l": r["l"]} for r in rows]
        label_count(rows, label_key="l", vocabulary=(1, 0))
        categorical_count(rows, column="l")
        self.assertEqual(rows, row_snapshot)
