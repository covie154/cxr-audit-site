# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Database-free coverage for the admin-controlled confidence intervals and display validation.

This suite exercises two Task-09 surfaces with the exact discipline the runbook froze:

* :mod:`report_v2.measurements.confidence` -- the 95% two-sided Wilson score interval
  (``z = 1.959963984540054``) together with the explicit ``(metric, method)`` CI registry.
  Only an *explicitly registered* proportion/method pair may publish a CI; balanced accuracy is a
  ``(sens + spec) / 2`` average, never a proportion, so any CI for it -- and any unregistered pair
  -- must fail with a typed :class:`UnsupportedCiError` **before** publication. ``n <= 0`` returns a
  null value with a reason (NEVER ``[0, 0]``); an out-of-range count raises a typed
  :class:`OutOfRangeCountError` (the input is never clamped).
* :mod:`report_v2.definitions.validation` -- the typed display/semantics guards: a Tukey box
  whisker is an observed value, NOT a confidence interval; a baseline band may never be
  computed/synthesised from widget data; a numeric benchmark is rejected on a non-numeric chart
  and on a unit mismatch; and the CI-OFF contract emits **no** ``ci``/``lower``/``upper`` keys at
  all.

The named Wilson hand-check table below was derived independently (see the runbook) and is asserted
to ``1e-5`` verbatim -- the code is never edited to match it; the values are the acceptance oracle.

Nothing here touches the ORM, the database, the web tier, clinical data or the reference snapshot:
the whole suite is :class:`django.test.SimpleTestCase`, the inputs are plain synthetic dicts and
integer counts, and the production static / SSL / mail configuration is overridden away so the run
is hermetic.
"""

from __future__ import annotations

import math

from django.test import SimpleTestCase, override_settings

from report_v2.measurements.confidence import (
    BALANCED_ACCURACY_IDENTITIES,
    DEFAULT_Z,
    ConfidenceError,
    OutOfRangeCountError,
    UnsupportedCiError,
    WilsonInterval,
    is_proportion_ci_registered,
    register_proportion_ci,
    require_proportion_ci,
    wilson_interval,
)
from report_v2.definitions.validation import (
    ALLOWED_BUCKET_KEYS,
    CI_RENDER_KEYS,
    NONNUMERIC_CHART_TYPES,
    NUMERIC_BENCHMARK_CHART_TYPES,
    BenchmarkUnitMismatchError,
    CalculatedBaselineBandError,
    CiOnUnknownMethodError,
    DisallowedGroupingError,
    DisplayValidationError,
    NumericBenchmarkOnNonNumericChartError,
    UnknownBucketError,
    UnknownColumnError,
    UnknownThresholdPolicyError,
    UnknownWidgetInputError,
    WhiskerIsConfidenceIntervalError,
    build_ci_render_keys,
    ensure_no_calculated_baseline_band,
    ensure_whisker_is_not_ci,
    validate_display,
    validate_numeric_benchmark,
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

#: The frozen acceptance table: ``(k, n) -> (lower, upper)`` at 95% two-sided Wilson. Derived
#: independently in the runbook; these are the ORACLE, asserted to ``1e-5`` (not to be edited to
#: match whatever the implementation happens to emit).
WILSON_HAND_CHECK = [
    ((0, 1), (0.0, 0.793451)),
    ((1, 1), (0.206549, 1.0)),
    ((1, 3), (0.061492, 0.792340)),
    ((2, 3), (0.207660, 0.938508)),
    ((5, 10), (0.236593, 0.763407)),
    ((0, 10), (0.0, 0.277533)),
    ((10, 10), (0.722467, 1.0)),
]

#: A metric name that is *deliberately* never registered anywhere in the suite, used to prove the
#: unregistered-pair rejection is real rather than a coincidence of shared registry state.
UNREGISTERED_METRIC = "unregistered_metric_task09_zulu"


def _reference_wilson(k, n, z=DEFAULT_Z):
    """An independent restatement of the Wilson formula, used only to cross-check invariants."""
    p = k / n
    z2 = z * z
    d = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / d
    half = z / d * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
    return max(0.0, center - half), min(1.0, center + half)


# ---------------------------------------------------------------------------
# A. The Wilson interval itself: the frozen hand-check table + invariants.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class WilsonIntervalTests(SimpleTestCase):
    """``wilson_interval`` reproduces the frozen table and keeps the invariants."""

    def test_hand_check_table_matches_to_1e_minus_5(self):
        """Every frozen ``(k, n) -> (lower, upper)`` row is asserted verbatim to ``1e-5``."""
        for (k, n), (want_low, want_up) in WILSON_HAND_CHECK:
            interval = wilson_interval(k, n)
            self.assertTrue(interval.available, f"({k},{n}) should be available")
            self.assertEqual(interval.method, "wilson")
            self.assertAlmostEqual(interval.confidence_level, 0.95, delta=1e-12)
            self.assertAlmostEqual(interval.lower, want_low, delta=1e-5,
                                   msg=f"lower mismatch for ({k},{n})")
            self.assertAlmostEqual(interval.upper, want_up, delta=1e-5,
                                  msg=f"upper mismatch for ({k},{n})")

    def test_every_supported_proportion_is_finite_ordered_and_in_range(self):
        """For every supported proportion the bounds are finite and ``0 <= lower <= upper <= 1``."""
        cases = [(k, n) for n in (1, 2, 3, 5, 10, 50) for k in range(n + 1)]
        for k, n in cases:
            interval = wilson_interval(k, n)
            self.assertTrue(interval.available)
            self.assertTrue(math.isfinite(interval.lower), f"lower not finite for ({k},{n})")
            self.assertTrue(math.isfinite(interval.upper), f"upper not finite for ({k},{n})")
            self.assertLessEqual(0.0, interval.lower)
            self.assertLessEqual(interval.lower, interval.upper)
            self.assertLessEqual(interval.upper, 1.0)
            # The result clamps into [0,1]; the reference restatement agrees to 1e-9.
            rl, ru = _reference_wilson(k, n)
            self.assertAlmostEqual(interval.lower, rl, delta=1e-9, msg=f"lower ref ({k},{n})")
            self.assertAlmostEqual(interval.upper, ru, delta=1e-9, msg=f"upper ref ({k},{n})")

    def test_default_z_is_the_frozen_95pct_value(self):
        """The documented 95% two-sided default ``z`` is ``1.959963984540054``."""
        self.assertEqual(DEFAULT_Z, 1.959963984540054)

    def test_result_is_clamped_into_unit_interval_never_the_input(self):
        """The *result* is clamped to [0,1]; the raw ``k``/``n`` are echoed unchanged."""
        edge = wilson_interval(1, 1)
        self.assertLessEqual(edge.upper, 1.0)
        self.assertGreaterEqual(edge.lower, 0.0)
        # The observed counts round-trip on the value object untouched.
        self.assertEqual((edge.k, edge.n), (1, 1))
        zero = wilson_interval(0, 1)
        self.assertEqual(zero.lower, 0.0)
        self.assertEqual((zero.k, zero.n), (0, 1))

    def test_value_object_is_frozen_and_has_the_documented_fields(self):
        """``WilsonInterval`` is an immutable value object with the frozen field set."""
        interval = wilson_interval(3, 10)
        for field in ("k", "n", "lower", "upper", "confidence_level", "method",
                      "available", "null_reason"):
            self.assertTrue(hasattr(interval, field), field)
        with self.assertRaises(Exception):
            interval.lower = 0.5  # type: ignore

    def test_n_le_zero_returns_null_with_reason_never_zero_band(self):
        """``n <= 0`` is a null value with a reason -- it is NEVER reported as ``[0, 0]``."""
        for n in (0, -1, -10):
            interval = wilson_interval(0, n)
            self.assertFalse(interval.available)
            self.assertIsNone(interval.lower)
            self.assertIsNone(interval.upper)
            self.assertIsNotNone(interval.null_reason)
            self.assertTrue(str(interval.null_reason).strip())
            # Explicitly not the forbidden fabricating [0,0] band.
            self.assertNotEqual((interval.lower, interval.upper), (0.0, 0.0))

    def test_out_of_range_count_raises_typed_error_never_clamps(self):
        """``k < 0`` or ``k > n`` raises the typed :class:`OutOfRangeCountError` (no clamping)."""
        for k, n in ((-1, 5), (6, 5), (-5, 5)):
            with self.assertRaises(OutOfRangeCountError) as ctx:
                wilson_interval(k, n)
            self.assertIsInstance(ctx.exception, ConfidenceError)


# ---------------------------------------------------------------------------
# B. The CI registry: explicit pairs only; balanced accuracy & unregistered pairs rejected.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class CiRegistryTests(SimpleTestCase):
    """Only explicitly registered ``(metric, method)`` pairs may publish a CI."""

    def test_registered_proportion_method_is_resolvable(self):
        register_proportion_ci("sensitivity")
        self.assertTrue(is_proportion_ci_registered("sensitivity"))
        self.assertIs(require_proportion_ci("sensitivity"), wilson_interval)

    def test_unregistered_metric_is_rejected_before_publication(self):
        """An unknown metric must fail with a typed :class:`UnsupportedCiError`."""
        self.assertFalse(is_proportion_ci_registered(UNREGISTERED_METRIC))
        with self.assertRaises(UnsupportedCiError) as ctx:
            require_proportion_ci(UNREGISTERED_METRIC)
        self.assertIsInstance(ctx.exception, ConfidenceError)

    def test_unregistered_method_string_is_rejected(self):
        """A known metric with an unregistered method string is still rejected."""
        register_proportion_ci("specificity")
        self.assertFalse(is_proportion_ci_registered("specificity", method="wald"))
        with self.assertRaises(UnsupportedCiError):
            require_proportion_ci("specificity", method="wald")

    def test_balanced_accuracy_cannot_be_registered_for_a_ci(self):
        """Balanced accuracy is a ``(sens+spec)/2`` average -- it has no per-proportion CI."""
        for spelling in sorted(BALANCED_ACCURACY_IDENTITIES):
            with self.assertRaises(UnsupportedCiError):
                register_proportion_ci(spelling)
            with self.assertRaises(UnsupportedCiError):
                require_proportion_ci(spelling)
        # ... nor any close spelling that normalises to the same identity.
        for alias in ("Balanced_Accuracy", "BALANCED ACCURACY"):
            with self.assertRaises(UnsupportedCiError):
                register_proportion_ci(alias)


# ---------------------------------------------------------------------------
# C. CI-OFF render contract: no ci/lower/upper keys are ever emitted.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class CiOffRenderContractTests(SimpleTestCase):
    """A widget with CI disabled carries NO ``ci``/``lower``/``upper`` keys at all."""

    def test_disabled_ci_emits_no_ci_keys(self):
        for config in ({}, {"ci": {"enabled": False}}, {"ci": {}}, {"ci": None}):
            rendered = build_ci_render_keys(config, lower=0.2, upper=0.8)
            self.assertEqual(rendered, {})
            self.assertFalse(set(rendered) & set(CI_RENDER_KEYS),
                             "CI-off render data must not carry ci/lower/upper keys")

    def test_validated_widget_with_ci_off_publishes_no_ci_keys(self):
        """End-to-end: a validated widget with CI off yields render data free of CI keys."""
        widget = {
            "type": "bar",
            "query": {"measurement": "positivity", "inputs": {"cohort_field": "site"}},
            "controls": {"date_range": True, "filters": ["site"], "compare_by": ["site"]},
            "ci": {"enabled": False, "method": "wilson"},
            "export": "summary",
        }
        validate_display(widget, allowed_inputs=frozenset({"cohort_field"}),
                         allowed_grouping=frozenset({"site"}), ci_methods=frozenset({"wilson"}))
        rendered = build_ci_render_keys(widget, lower=0.3, upper=0.6)
        self.assertNotIn("ci", rendered)
        self.assertNotIn("lower", rendered)
        self.assertNotIn("upper", rendered)

    def test_enabled_ci_emits_ordered_bounds_and_ci_metadata(self):
        rendered = build_ci_render_keys({"ci": {"enabled": True, "method": "wilson"}},
                                        lower=0.2, upper=0.8, confidence_level=0.95)
        self.assertEqual(set(rendered), {"ci", "lower", "upper"})
        self.assertEqual(rendered["lower"], 0.2)
        self.assertEqual(rendered["upper"], 0.8)
        self.assertEqual(rendered["ci"]["method"], "wilson")
        self.assertEqual(rendered["ci"]["confidence_level"], 0.95)
        self.assertTrue(rendered["ci"]["enabled"])

    def test_enabled_ci_rejects_unordered_or_out_of_range_bounds(self):
        for lower, upper in ((0.8, 0.2), (-0.1, 0.5), (0.5, 1.5), (float("nan"), 0.5),
                             (0.2, float("inf"))):
            with self.assertRaises(DisplayValidationError):
                build_ci_render_keys({"ci": {"enabled": True}}, lower=lower, upper=upper)


# ---------------------------------------------------------------------------
# D. Whiskers are observed values, never a confidence interval.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class WhiskerIsNotConfidenceIntervalTests(SimpleTestCase):
    """A Tukey box whisker is an observed datum -- presenting it as a CI is rejected."""

    def test_boxplot_whisker_labelled_as_ci_is_rejected(self):
        config = {
            "type": "boxplot",
            "options": {"whiskers": "tukey", "whisker_is_ci": True},
            "ci": {"enabled": True},
        }
        with self.assertRaises(WhiskerIsConfidenceIntervalError) as ctx:
            ensure_whisker_is_not_ci(config)
        self.assertIsInstance(ctx.exception, DisplayValidationError)

    def test_whisker_style_claiming_confidence_semantics_is_rejected(self):
        for style in ("tukey_ci", "confidence_whisker", "ci_whiskers"):
            with self.assertRaises(WhiskerIsConfidenceIntervalError):
                ensure_whisker_is_not_ci({"type": "boxplot", "options": {"whiskers": style}})

    def test_genuine_tukey_whiskers_with_independent_ci_still_pass(self):
        """Whiskers and a legitimate CI may coexist when they are NOT conflated (no marker)."""
        config = {
            "type": "boxplot",
            "options": {"whiskers": "tukey"},
            "ci": {"enabled": True, "method": "wilson"},
        }
        ensure_whisker_is_not_ci(config)  # must not raise


# ---------------------------------------------------------------------------
# E. Baseline bands must reference registered data, never be synthesised.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class NoCalculatedBaselineBandTests(SimpleTestCase):
    """A baseline band may never be computed/synthesised from the widget's own data."""

    def test_computed_baseline_band_is_rejected(self):
        for marker in ("computed", "from_data", "derived", "synthetic", "generated", "auto"):
            with self.assertRaises(CalculatedBaselineBandError):
                ensure_no_calculated_baseline_band({"baseline": {marker: True}})
        with self.assertRaises(CalculatedBaselineBandError):
            ensure_no_calculated_baseline_band({"baseline_band": {"calculate": True}})

    def test_baseline_referencing_registered_data_is_allowed(self):
        ensure_no_calculated_baseline_band({"baseline": {"measurement": "positivity"}})
        ensure_no_calculated_baseline_band({"baseline": {"policy": "default_policy"}})

    def test_explicit_constant_baseline_with_unit_is_allowed(self):
        ensure_no_calculated_baseline_band({"baseline": {"label": "Target", "value": 0.9, "unit": "%"}})

    def test_baseline_with_nothing_registered_and_no_constant_is_rejected(self):
        with self.assertRaises(CalculatedBaselineBandError):
            ensure_no_calculated_baseline_band({"baseline": {"label": "Mystery"}})


# ---------------------------------------------------------------------------
# F. Numeric benchmarks: chart-type and unit discipline.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class NumericBenchmarkTests(SimpleTestCase):
    """Numeric benchmarks only make sense on numeric charts with matching units."""

    def test_numeric_benchmark_on_nonnumeric_chart_is_rejected(self):
        for chart in sorted(NONNUMERIC_CHART_TYPES):
            config = {"type": chart, "benchmarks": [{"label": "L", "value": 0.8, "unit": "%"}]}
            with self.assertRaises(NumericBenchmarkOnNonNumericChartError):
                validate_numeric_benchmark(config)

    def test_numeric_benchmark_on_unknown_chart_is_rejected(self):
        config = {"type": "sparkline", "benchmarks": [{"label": "L", "value": 1.0, "unit": "%"}]}
        with self.assertRaises(NumericBenchmarkOnNonNumericChartError):
            validate_numeric_benchmark(config)

    def test_numeric_benchmark_on_numeric_chart_passes(self):
        for chart in sorted(NUMERIC_BENCHMARK_CHART_TYPES):
            config = {"type": chart, "benchmarks": [{"label": "L", "value": 1.0, "unit": "%"}]}
            validate_numeric_benchmark(config)  # must not raise

    def test_unit_mismatch_is_rejected(self):
        config = {"type": "bar", "benchmarks": [{"label": "L", "value": 5.0, "unit": "%"}]}
        with self.assertRaises(BenchmarkUnitMismatchError):
            validate_numeric_benchmark(config, chart_type="bar", measure_unit="seconds")

    def test_unit_match_ignores_case_and_whitespace(self):
        config = {"type": "bar", "benchmarks": [{"label": "L", "value": 5.0, "unit": "  % "}]}
        validate_numeric_benchmark(config, chart_type="bar", measure_unit="%")  # must not raise

    def test_missing_or_empty_benchmarks_pass(self):
        validate_numeric_benchmark({"type": "bar"})
        validate_numeric_benchmark({"type": "bar", "benchmarks": []})

    def test_malformed_benchmark_value_is_rejected(self):
        for bad in (True, "0.5", float("nan"), float("inf")):
            config = {"type": "bar", "benchmarks": [{"label": "L", "value": bad, "unit": "%"}]}
            with self.assertRaises(DisplayValidationError):
                validate_numeric_benchmark(config, chart_type="bar")


# ---------------------------------------------------------------------------
# G. validate_display covers inputs / columns / buckets / thresholds / units / grouping.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ValidateDisplayTests(SimpleTestCase):
    """The composite display validator rejects each off-definition axis independently."""

    def _base_widget(self, **overrides):
        widget = {
            "type": "bar",
            "query": {"measurement": "positivity", "inputs": {"cohort_field": "site"},
                      "threshold_policy": "default_policy"},
            "controls": {"date_range": True, "filters": ["site"], "compare_by": ["site"]},
            "columns": ["site", "count"],
            "bucket": "week",
            "export": "summary",
            "ci": {"enabled": False},
        }
        widget.update(overrides)
        return widget

    def _validate(self, widget, **kw):
        defaults = dict(
            allowed_inputs=frozenset({"cohort_field"}),
            declared_columns=frozenset({"site", "count"}),
            allowed_buckets=ALLOWED_BUCKET_KEYS,
            declared_threshold_policies=frozenset({"default_policy"}),
            allowed_grouping=frozenset({"site"}),
            measure_unit=None,
            ci_methods=frozenset({"wilson"}),
        )
        defaults.update(kw)
        validate_display(widget, **defaults)

    def test_a_fully_conforming_widget_passes(self):
        self._validate(self._base_widget())  # must not raise

    def test_unknown_input_is_rejected(self):
        widget = self._base_widget(query={"measurement": "positivity",
                                          "inputs": {"ghost_field": "site"}})
        with self.assertRaises(UnknownWidgetInputError):
            self._validate(widget)

    def test_unknown_column_is_rejected(self):
        with self.assertRaises(UnknownColumnError):
            self._validate(self._base_widget(columns=["site", "secret"]))

    def test_unknown_bucket_is_rejected(self):
        with self.assertRaises(UnknownBucketError):
            self._validate(self._base_widget(bucket="fortnight"))

    def test_unknown_threshold_policy_is_rejected(self):
        widget = self._base_widget(query={"measurement": "positivity",
                                         "inputs": {"cohort_field": "site"},
                                         "threshold_policy": "rogue_policy"})
        with self.assertRaises(UnknownThresholdPolicyError):
            self._validate(widget)

    def test_disallowed_grouping_is_rejected(self):
        widget = self._base_widget(controls={"date_range": True, "filters": [],
                                             "compare_by": ["attending"]})
        with self.assertRaises(DisallowedGroupingError):
            self._validate(widget)

    def test_disallowed_default_compare_by_is_rejected(self):
        with self.assertRaises(DisallowedGroupingError):
            self._validate(self._base_widget(default_compare_by="attending"))

    def test_benchmark_unit_mismatch_surfaces_through_validate_display(self):
        widget = self._base_widget(benchmarks=[{"label": "Target", "value": 5.0, "unit": "%"}])
        with self.assertRaises(BenchmarkUnitMismatchError):
            self._validate(widget, measure_unit="seconds")

    def test_ci_on_unknown_method_is_rejected(self):
        widget = self._base_widget(ci={"enabled": True, "method": "wald"})
        with self.assertRaises(CiOnUnknownMethodError):
            self._validate(widget, ci_methods=frozenset({"wilson"}))

    def test_non_mapping_config_is_rejected(self):
        for bad in (None, [], "bar", 7):
            with self.assertRaises(DisplayValidationError):
                validate_display(bad)
