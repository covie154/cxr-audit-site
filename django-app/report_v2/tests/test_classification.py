# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused, database-free coverage for the report-v2 classification measurement layer.

These exercise the pure computation entry points in :mod:`report_v2.measurements.classification`: the binary
confusion counts and the seven documented rates, the null-plus-reason contract for every zero-denominator
ratio, the NxN confusion matrix laid out by a *stable declared* class order, target-class one-versus-rest
rates, and the single aggregate entry point -- all pinned against the runbook's two hand-checkable blocks and
its eight DONE-WHEN guarantees:

* the binary block reproduces exactly (TP=2, FN=1, FP=1, TN=2; the six rates = 2/3; predicted-negative
  fraction = 3/6), an in-coverage row with a missing ground truth is excluded without moving any metric, and
  the exclusion reasons stay non-overlapping and reconcile (``matching == eligible + exclusions``);
* a rate whose denominator is zero is ``None`` with a stated reason -- **never** ``0``/``0.0`` -- while a
  genuine ``0.0`` over a positive denominator stays a defined zero, so the suite proves the two are distinct;
* the multiclass block reproduces exactly (matrix ``[[1,1,0],[0,1,1],[1,0,1]]``, accuracy 1/2, class-A
  sensitivity 1/2 / specificity 3/4), the matrix geometry follows the declared order (not data-encounter
  order), and a multiclass rate without an explicit target class fails validation *before* any counting;
* balanced accuracy is labelled exactly ``Balanced accuracy`` and is never (anywhere in the module) named for
  a score-ranking statistic; no score-ranking / threshold-sweep / macro-average capability is introduced.

No database, ORM, real/clinical data or the reference snapshot are touched: the whole suite is
:class:`django.test.SimpleTestCase`, the populations are the synthetic in-memory ``factories`` lifted through
``pairs_from_rows``, and PRIME is read only through the frozen catalog. The production static / SSL / mail
configuration is overridden away so the suite is hermetic.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import json
import re

from django.test import SimpleTestCase, override_settings

from report_v2.measurements import classification as classification_module
from report_v2.measurements.classification import (
    BALANCED_ACCURACY_LABEL,
    BinaryClassVocabulary,
    BinaryClassificationMetrics,
    BinaryConfusionCounts,
    ClassificationError,
    ClassificationSummary,
    ConfusionMatrix,
    EmptyPopulationError,
    IncompatiblePairError,
    InvalidClassOrderError,
    MissingTargetClassError,
    OutOfVocabularyClassError,
    Rate,
    TargetClassMetrics,
    binary_classification_metrics,
    binary_confusion_counts,
    classification_summary,
    confusion_matrix,
    one_vs_rest_metrics,
    pairs_from_rows,
    require_target_class,
    safe_rate,
    vocabulary_from_outcome,
)
from report_v2.projects import base, prime
from report_v2.tests.factories import (
    binary_fixture,
    binary_fixture_no_positive_gt,
    binary_fixture_with_missing_gt,
    three_class_fixture,
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# The binary vocabulary the in-memory factories encode (gt_label / pred_label are ints 1/0/None).
_VOCAB = BinaryClassVocabulary(positive_class=1, negative_class=0)
# The multiclass factories use string classes A/B/C on gt_class / pred_class; the declared order is A,B,C.
_CLASSES = ("A", "B", "C")


def _pairs(fixture, gt_key, pred_key):
    """Lift a factory fixture into ordered ``(ground_truth, prediction)`` pairs (read-only convenience)."""
    return pairs_from_rows(fixture, ground_truth_key=gt_key, prediction_key=pred_key)


def _binary_pairs():
    return _pairs(binary_fixture(), "gt_label", "pred_label")


def _three_class_pairs():
    return _pairs(three_class_fixture(), "gt_class", "pred_class")


def _walk_keys(node):
    """Return every dict key reachable at any depth inside a JSON-ish value (for the naming scan)."""
    keys = []
    if isinstance(node, dict):
        for key, value in node.items():
            keys.append(key)
            keys.extend(_walk_keys(value))
    elif isinstance(node, (list, tuple)):
        for item in node:
            keys.extend(_walk_keys(item))
    return keys


# ---------------------------------------------------------------------------
# A. Binary hand-check reproduction.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class BinaryHandCheckTests(SimpleTestCase):
    """The runbook "Binary comparison" block reproduces value-for-value."""

    def test_hand_check_binary_block_reproduces_exactly(self):
        metrics = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        counts = metrics.counts
        self.assertEqual((counts.tp, counts.fn, counts.fp, counts.tn), (2, 1, 1, 2))
        self.assertEqual(counts.eligible, 6)
        self.assertEqual(counts.matching, 6)
        self.assertEqual(counts.exclusions, 0)
        six_rates = ("accuracy", "sensitivity", "specificity", "ppv", "npv", "balanced_accuracy")
        for name in six_rates:
            rate = metrics.rate(name)
            with self.subTest(metric=name):
                self.assertTrue(rate.defined)
                self.assertAlmostEqual(rate.value, 2 / 3, places=12)
        # The raw counts reduce to 2/3 for accuracy but the stored operands are the honest (tp+tn)/n.
        self.assertEqual((metrics.accuracy.numerator, metrics.accuracy.denominator), (4, 6))
        for name in ("sensitivity", "specificity", "ppv", "npv", "balanced_accuracy"):
            rate = metrics.rate(name)
            with self.subTest(metric=name):
                self.assertEqual(rate.numerator, 2)
                self.assertEqual(rate.denominator, 3)
        pnf = metrics.rate("predicted_negative_fraction")
        self.assertEqual(pnf.numerator, 3)
        self.assertEqual(pnf.denominator, 6)

    def test_predicted_negative_fraction_uses_the_group_denominator(self):
        metrics = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        counts = metrics.counts
        pnf = metrics.rate("predicted_negative_fraction")
        self.assertEqual(pnf.denominator, counts.eligible)
        self.assertNotEqual(pnf.denominator, counts.negative_cases)
        self.assertNotEqual(pnf.denominator, counts.predicted_negatives)
        # sensitivity's own denominator (tp + fn) is the positive-case count, distinct from the group n.
        self.assertEqual(metrics.sensitivity.denominator, counts.tp + counts.fn)
        self.assertNotEqual(metrics.sensitivity.denominator, counts.eligible)

    def test_missing_ground_truth_row_is_excluded_and_does_not_move_the_metrics(self):
        baseline = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        with_missing = binary_classification_metrics(
            _pairs(binary_fixture_with_missing_gt(), "gt_label", "pred_label"), vocabulary=_VOCAB
        )
        self.assertEqual(with_missing.counts.matching, 7)
        self.assertEqual(with_missing.counts.eligible, 6)
        self.assertEqual(with_missing.counts.exclusions, 1)
        self.assertEqual(dict(with_missing.counts.excluded), {"missing_ground_truth": 1})
        for name, rate in baseline.rates.items():
            self.assertEqual(with_missing.rates[name].as_dict(), rate.as_dict())
        # Only the four confusion cells (and the eligible group n) are unchanged by the excluded row.
        for field in ("tp", "fn", "fp", "tn", "eligible"):
            self.assertEqual(getattr(with_missing.counts, field), getattr(baseline.counts, field))

    def test_exclusion_reason_counts_are_non_overlapping_and_reconcile(self):
        missing_gt = binary_confusion_counts(
            _pairs(binary_fixture_with_missing_gt(), "gt_label", "pred_label"), vocabulary=_VOCAB
        )
        self.assertEqual(missing_gt.eligible + missing_gt.exclusions, missing_gt.matching)
        self.assertEqual(sum(missing_gt.excluded.values()), missing_gt.exclusions)
        # An all-None-prediction variant built inline: every reason is missing_prediction, one bucket only.
        all_none_pred = [(1, None), (1, None), (0, None), (0, None)]
        counts = binary_confusion_counts(all_none_pred, vocabulary=_VOCAB)
        self.assertEqual(dict(counts.excluded), {"missing_prediction": 4})
        self.assertEqual(counts.eligible, 0)
        self.assertEqual(counts.matching, 4)
        self.assertEqual(counts.exclusions, 4)
        self.assertEqual(counts.eligible + counts.exclusions, counts.matching)
        # Both-absent rows attribute to the ground-truth reason alone (non-overlapping buckets).
        both_absent = [(None, None), (None, 1), (1, None)]
        merged = binary_confusion_counts(both_absent, vocabulary=_VOCAB)
        self.assertEqual(dict(merged.excluded), {"missing_ground_truth": 2, "missing_prediction": 1})
        self.assertEqual(merged.exclusions, 3)


# ---------------------------------------------------------------------------
# B. Zero denominators are null with a reason, never zero.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ZeroDenominatorNullTests(SimpleTestCase):
    """Undefined rates stay ``None`` with a stated reason; genuine zeros remain defined ``0.0``."""

    def test_removing_all_gt_positives_makes_sensitivity_null_not_zero(self):
        metrics = binary_classification_metrics(
            _pairs(binary_fixture_no_positive_gt(), "gt_label", "pred_label"), vocabulary=_VOCAB
        )
        sensitivity = metrics.sensitivity
        self.assertIsNone(sensitivity.value)
        self.assertIsInstance(sensitivity.null_reason, str)
        self.assertTrue(sensitivity.null_reason)
        self.assertIn("sensitivity", sensitivity.null_reason.lower())
        self.assertIn("zero denominator", sensitivity.null_reason.lower())
        self.assertEqual(sensitivity.numerator, 0)
        self.assertEqual(sensitivity.denominator, 0)
        self.assertIsNot(sensitivity.value, 0)
        self.assertNotEqual(repr(sensitivity.value), "0")
        self.assertFalse(sensitivity.defined)
        # balanced accuracy inherits the undefined component and names it.
        self.assertIsNone(metrics.balanced_accuracy.value)
        self.assertTrue(metrics.balanced_accuracy.null_reason)
        self.assertIn("sensitivity", metrics.balanced_accuracy.null_reason.lower())
        # ppv is a LEGITIMATE 0.0: tp/(tp+fp) = 0/3, its denominator is positive.
        self.assertEqual(metrics.ppv.value, 0.0)
        self.assertTrue(metrics.ppv.defined)
        self.assertIsNone(metrics.ppv.null_reason)
        self.assertEqual(metrics.ppv.numerator, 0)
        self.assertEqual(metrics.ppv.denominator, 3)

    def test_positive_case_denominator_is_kept_distinct_from_the_group_count(self):
        counts = binary_confusion_counts(
            _pairs(binary_fixture_no_positive_gt(), "gt_label", "pred_label"), vocabulary=_VOCAB
        )
        metrics = binary_classification_metrics(
            _pairs(binary_fixture_no_positive_gt(), "gt_label", "pred_label"), vocabulary=_VOCAB
        )
        self.assertEqual(counts.eligible, 6)
        self.assertEqual(counts.positive_cases, 0)
        self.assertNotEqual(counts.eligible, counts.positive_cases)
        self.assertEqual(metrics.accuracy.denominator, 6)
        self.assertEqual(metrics.sensitivity.denominator, 0)

    def test_zero_denominator_never_becomes_a_zero_estimate(self):
        populations = {
            "all_negative": [(0, 0), (0, 0), (0, 0)],
            "all_positive": [(1, 1), (1, 1), (1, 1)],
            "no_predicted_positives": [(1, 0), (0, 0), (1, 0)],
            "no_predicted_negatives": [(1, 1), (0, 1), (1, 1)],
            "single_tp": [(1, 1)],
            "single_tn": [(0, 0)],
        }
        for name, pairs in populations.items():
            metrics = binary_classification_metrics(pairs, vocabulary=_VOCAB)
            for metric_name, rate in metrics.rates.items():
                with self.subTest(population=name, metric=metric_name):
                    if rate.denominator == 0:
                        self.assertIsNone(rate.value)
                        self.assertIsNot(rate.value, 0)
                        self.assertTrue(rate.null_reason)
                        self.assertFalse(rate.defined)
                    if rate.value is None:
                        self.assertTrue(rate.null_reason)
        # A zero numerator over a positive denominator is a genuine 0.0 -- the two cases must differ.
        undefined = safe_rate("x", 0, 0)
        genuine_zero = safe_rate("x", 0, 5)
        self.assertIsNone(undefined.value)
        self.assertEqual(genuine_zero.value, 0.0)
        self.assertNotEqual(undefined.value, genuine_zero.value)

    def test_safe_rate_rejects_invalid_operands(self):
        for numerator, denominator in (
            (-1, 5), (5, -1), (True, 5), (5, True), (1.5, 5), (5, 1.5), ("1", 5),
        ):
            with self.subTest(numerator=numerator, denominator=denominator):
                with self.assertRaises(ClassificationError) as ctx:
                    safe_rate("x", numerator, denominator)
                self.assertEqual(ctx.exception.kind, "invalid-rate-operand")


# ---------------------------------------------------------------------------
# C. Multiclass matrix + one-versus-rest.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class MulticlassMatrixTests(SimpleTestCase):
    """The runbook "Multiclass" block reproduces and the declared order is authoritative."""

    def test_hand_check_multiclass_block_reproduces_exactly(self):
        matrix = confusion_matrix(_three_class_pairs(), classes=_CLASSES)
        self.assertEqual(matrix.cells, ((1, 1, 0), (0, 1, 1), (1, 0, 1)))
        self.assertEqual(matrix.rows_are, "ground_truth")
        self.assertEqual(matrix.columns_are, "prediction")
        self.assertEqual(matrix.n, 6)
        self.assertEqual(matrix.accuracy.numerator, 3)
        self.assertEqual(matrix.accuracy.denominator, 6)
        self.assertAlmostEqual(matrix.accuracy.value, 0.5, places=12)
        self.assertEqual(matrix.row_totals, (2, 2, 2))
        self.assertEqual(matrix.column_totals, (2, 2, 2))

    def test_target_class_one_vs_rest_rates_for_class_a(self):
        target = one_vs_rest_metrics(_three_class_pairs(), classes=_CLASSES, target_class="A")
        self.assertEqual((target.tp, target.fn, target.fp, target.tn), (1, 1, 1, 3))
        self.assertEqual((target.sensitivity.numerator, target.sensitivity.denominator), (1, 2))
        self.assertEqual((target.specificity.numerator, target.specificity.denominator), (3, 4))
        self.assertEqual((target.ppv.numerator, target.ppv.denominator), (1, 2))
        self.assertEqual((target.npv.numerator, target.npv.denominator), (3, 4))
        self.assertEqual(target.eligible, 6)

    def test_declared_class_order_is_stable_and_not_data_encounter_order(self):
        swapped = ("A", "C", "B")
        matrix = confusion_matrix(_three_class_pairs(), classes=swapped)
        self.assertEqual(matrix.classes, swapped)
        # Rows/columns follow the declared order, so swapping B<->C permutes them consistently.
        self.assertEqual(matrix.cells, ((1, 0, 1), (1, 1, 0), (0, 1, 1)))
        self.assertEqual(matrix.row_totals, (2, 2, 2))
        self.assertEqual(matrix.column_totals, (2, 2, 2))

    def test_cell_lookups_follow_declared_geometry(self):
        matrix = confusion_matrix(_three_class_pairs(), classes=_CLASSES)
        self.assertEqual(matrix.cell("A", "A"), 1)
        self.assertEqual(matrix.cell("A", "B"), 1)
        self.assertEqual(matrix.cell("A", "C"), 0)
        self.assertEqual(matrix.cell("B", "A"), 0)
        self.assertEqual(matrix.cell("C", "A"), 1)

    def test_matrix_without_any_eligible_pair_has_null_accuracy(self):
        # Every pair excluded (absent predictions) -> n == 0 -> accuracy is null with a reason, never 0.
        excluded_only = [("A", None), ("B", None)]
        matrix = confusion_matrix(excluded_only, classes=_CLASSES)
        self.assertEqual(matrix.n, 0)
        self.assertIsNone(matrix.accuracy.value)
        self.assertTrue(matrix.accuracy.null_reason)


# ---------------------------------------------------------------------------
# D. Validation guards.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ValidationGuardTests(SimpleTestCase):
    """Every guard fails loudly before any counting, with a typed error."""

    def test_multiclass_rate_without_target_class_fails_validation(self):
        pairs = _three_class_pairs()
        # Missing required keyword argument entirely -> TypeError at call time.
        with self.assertRaises(TypeError):
            one_vs_rest_metrics(pairs, classes=_CLASSES)
        # Summary entry point with no target class -> MissingTargetClassError.
        for bad in (None, "", "   "):
            with self.subTest(target=bad):
                with self.assertRaises(MissingTargetClassError) as ctx:
                    classification_summary(pairs, classes=_CLASSES, target_class=bad)
                message = str(ctx.exception).lower()
                self.assertIn("target", message)
                self.assertIn("averag", message)

    def test_missing_target_class_validation_precedes_counting(self):
        # A population that also contains an out-of-vocabulary value: the *missing target* guard must win.
        poisoned = list(_three_class_pairs()) + [("D", "A")]
        with self.assertRaises(MissingTargetClassError):
            classification_summary(poisoned, classes=_CLASSES)  # no target_class
        with self.assertRaises(MissingTargetClassError):
            one_vs_rest_metrics(poisoned, classes=_CLASSES, target_class="")

    def test_no_unqualified_multiclass_sensitivity_is_exposed(self):
        summary = classification_summary(_three_class_pairs(), classes=_CLASSES, target_class="A")
        view = summary.as_dict()
        for bare in ("sensitivity", "specificity", "ppv", "npv"):
            self.assertNotIn(bare, view)
        # Those rates live under the target view, which always carries the target class.
        self.assertIn("target_class", view["target"])
        self.assertEqual(view["target"]["target_class"], "A")
        for key in ("sensitivity", "specificity", "ppv", "npv"):
            self.assertIn(key, view["target"])

    def test_matrix_rejects_out_of_vocabulary_classes(self):
        with self.assertRaises(OutOfVocabularyClassError) as ctx:
            confusion_matrix([("D", "A")], classes=_CLASSES)
        message = str(ctx.exception)
        self.assertIn("D", message)
        self.assertIn("ground truth", message)
        self.assertEqual(ctx.exception.kind, "out-of-vocabulary-class")
        self.assertTrue(str(ctx.exception).startswith("[out-of-vocabulary-class]"))

    def test_binary_rejects_out_of_vocabulary_labels(self):
        with self.assertRaises(OutOfVocabularyClassError) as ctx:
            binary_confusion_counts([(2, 1)], vocabulary=_VOCAB)
        self.assertIn("ground truth", str(ctx.exception))
        with self.assertRaises(OutOfVocabularyClassError) as ctx:
            binary_confusion_counts([(1, "abnormal")], vocabulary=_VOCAB)
        self.assertIn("prediction", str(ctx.exception))

    def test_bool_is_not_silently_accepted_as_a_binary_class(self):
        # Declared vocabulary is ints (1/0); a bool must not be read as the int 1.
        with self.assertRaises(OutOfVocabularyClassError):
            binary_confusion_counts([(True, 1)], vocabulary=_VOCAB)

    def test_vocabulary_from_outcome_and_inline_outcome(self):
        outcome = base.Outcome("abnormal_demo", ("normal", "abnormal"), "abnormal")
        vocabulary = vocabulary_from_outcome(outcome)
        self.assertEqual(vocabulary.classes, ("abnormal", "normal"))
        self.assertEqual(vocabulary.positive_class, "abnormal")
        self.assertEqual(vocabulary.negative_class, "normal")
        # Shipped PRIME outcomes are binary and yield a vocabulary with the abnormal positive class.
        self.assertEqual(len(prime.OUTCOMES["abnormal_lunit"].classes), 2)
        derived = vocabulary_from_outcome(prime.OUTCOMES["abnormal_lunit"])
        self.assertEqual(derived.positive_class, "abnormal")
        self.assertEqual(derived.classes, ("abnormal", "normal"))

    def test_non_binary_outcome_rejected_for_vocabulary(self):
        ternary = base.Outcome("tri", ("A", "B", "C"), "C")
        with self.assertRaises(InvalidClassOrderError):
            vocabulary_from_outcome(ternary)

    def test_invalid_class_order_rejected(self):
        pairs = _three_class_pairs()
        with self.assertRaises(InvalidClassOrderError):
            confusion_matrix(pairs, classes=())            # empty
        with self.assertRaises(InvalidClassOrderError):
            confusion_matrix(pairs, classes=("A", "A", "B"))  # duplicates
        # Chosen behaviour for an unhashable member: it is a malformed *class order*, so InvalidClassOrderError.
        with self.assertRaises(InvalidClassOrderError):
            confusion_matrix(pairs, classes=["A", ["B"]])

    def test_equal_vocabulary_classes_rejected(self):
        with self.assertRaises(ClassificationError) as ctx:
            BinaryClassVocabulary(positive_class="x", negative_class="x")
        self.assertEqual(ctx.exception.kind, "invalid-vocabulary")

    def test_binary_and_classes_mutually_exclusive(self):
        with self.assertRaises(ClassificationError) as ctx:
            classification_summary(
                _binary_pairs(), vocabulary=_VOCAB, classes=_CLASSES, target_class="A"
            )
        self.assertEqual(ctx.exception.kind, "invalid-summary-request")

    def test_summary_requires_exactly_one_of_vocabulary_or_classes(self):
        with self.assertRaises(ClassificationError) as ctx:
            classification_summary(_binary_pairs())
        self.assertEqual(ctx.exception.kind, "invalid-summary-request")

    def test_empty_population_raises_typed_error(self):
        with self.assertRaises(EmptyPopulationError):
            binary_confusion_counts([], vocabulary=_VOCAB)

    def test_incompatible_pair_containers_rejected(self):
        with self.assertRaises(IncompatiblePairError):
            binary_confusion_counts([(1, 0, 1)], vocabulary=_VOCAB)  # 3-item row
        with self.assertRaises(IncompatiblePairError):
            binary_confusion_counts([5], vocabulary=_VOCAB)          # bare int row

    def test_require_target_class_helper(self):
        self.assertEqual(require_target_class("B", classes=_CLASSES), "B")
        with self.assertRaises(MissingTargetClassError):
            require_target_class(None, classes=_CLASSES)
        with self.assertRaises(MissingTargetClassError):
            require_target_class("   ", classes=_CLASSES)
        with self.assertRaises(OutOfVocabularyClassError):
            require_target_class("Z", classes=_CLASSES)


# ---------------------------------------------------------------------------
# E. Naming / scope frozen product decisions.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class NamingAndScopeTests(SimpleTestCase):
    """Balanced accuracy naming, the no-score-ranking scope and the purity of the module."""

    def _source(self):
        return inspect.getsource(classification_module)

    def test_balanced_accuracy_is_labelled_balanced_accuracy_and_never_roc_auc(self):
        self.assertEqual(BALANCED_ACCURACY_LABEL, "Balanced accuracy")
        self.assertEqual(classification_module.BALANCED_ACCURACY_LABEL, "Balanced accuracy")
        metrics = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        self.assertEqual(metrics.balanced_accuracy.label, BALANCED_ACCURACY_LABEL)
        as_dict = metrics.as_dict()
        self.assertIn("balanced_accuracy", as_dict)
        for key in _walk_keys(as_dict):
            lowered = str(key).lower()
            self.assertNotIn("auc", lowered)
            self.assertNotIn("roc", lowered)
        # Module source scan (classification.py only): no forbidden score-ranking words.
        source = self._source()
        self.assertNotIn("auc", source.lower())
        self.assertIsNone(re.search(r"(?i)(?<![A-Za-z])roc(?![A-Za-z])", source))
        self.assertIsNone(re.search(r"(?i)(?<![A-Za-z])a-u-c(?![A-Za-z])", source))
        # No exported name or value-object field carries the forbidden substrings.
        for name in dir(classification_module):
            lowered = name.lower()
            self.assertNotIn("auc", lowered)
            self.assertNotIn("roc", lowered)
        for cls in (Rate, BinaryClassificationMetrics, TargetClassMetrics, ConfusionMatrix, ClassificationSummary):
            for field in dataclasses.fields(cls):
                self.assertNotIn("auc", field.name.lower())
                self.assertNotIn("roc", field.name.lower())

    def test_no_roc_auc_or_cross_class_averaging_api_is_introduced(self):
        forbidden = {"auc", "roc", "tpr", "fpr", "curve", "sweep", "macro", "mean_over",
                     "average_classes", "average_across"}
        for name in dir(classification_module):
            lowered = name.lower()
            for token in forbidden:
                self.assertNotIn(token, lowered)
        public_average = [
            name for name in dir(classification_module)
            if not name.startswith("_") and "average" in name.lower() and callable(getattr(classification_module, name))
        ]
        self.assertEqual(public_average, [])

    def test_balanced_accuracy_is_the_mean_of_sensitivity_and_specificity(self):
        from fractions import Fraction

        metrics = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        expected = (
            Fraction(metrics.sensitivity.numerator, metrics.sensitivity.denominator)
            + Fraction(metrics.specificity.numerator, metrics.specificity.denominator)
        ) / 2
        actual = Fraction(metrics.balanced_accuracy.numerator, metrics.balanced_accuracy.denominator)
        self.assertEqual(actual, expected)

    def test_no_module_level_django_or_orm_import(self):
        source = self._source().lower()
        for token in (
            "import django", "from django", "upload.models", "cxrstudy", "connections",
            "open(", "requests", "socket", "subprocess",
        ):
            self.assertNotIn(token, source)
        for banned in ("django", "upload", "CXrStudy", "CXRStudy", "open", "requests", "socket", "subprocess"):
            self.assertNotIn(banned, classification_module.__dict__)


# ---------------------------------------------------------------------------
# F. Reuse / purity.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class ReuseAndPurityTests(SimpleTestCase):
    """The aggregate is a thin composition of the shared primitives; inputs are never mutated."""

    def test_classification_summary_uses_the_same_primitives(self):
        direct = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        summary = classification_summary(_binary_pairs(), vocabulary=_VOCAB)
        self.assertIsInstance(summary, ClassificationSummary)
        self.assertEqual(summary.kind, "binary")
        for name, rate in direct.rates.items():
            self.assertEqual(summary.metrics.rate(name).as_dict(), rate.as_dict())
        for field in dataclasses.fields(BinaryConfusionCounts):
            self.assertEqual(getattr(summary.counts, field.name), getattr(direct.counts, field.name))

        # Multiclass: the summary's matrix / target agree with the standalone primitives.
        matrix = confusion_matrix(_three_class_pairs(), classes=_CLASSES)
        target = one_vs_rest_metrics(_three_class_pairs(), classes=_CLASSES, target_class="B")
        multi = classification_summary(_three_class_pairs(), classes=_CLASSES, target_class="B")
        self.assertEqual(multi.kind, "multiclass")
        self.assertEqual(multi.matrix.cells, matrix.cells)
        for name in ("sensitivity", "specificity", "ppv", "npv"):
            self.assertEqual(getattr(multi.target, name).as_dict(), getattr(target, name).as_dict())

    def test_metrics_are_pure_and_inputs_not_mutated(self):
        fixtures = {
            "binary": (_binary_pairs(), lambda p: binary_classification_metrics(p, vocabulary=_VOCAB)),
            "missing_gt": (
                _pairs(binary_fixture_with_missing_gt(), "gt_label", "pred_label"),
                lambda p: binary_classification_metrics(p, vocabulary=_VOCAB),
            ),
            "three": (_three_class_pairs(), lambda p: confusion_matrix(p, classes=_CLASSES)),
            "target": (_three_class_pairs(), lambda p: one_vs_rest_metrics(p, classes=_CLASSES, target_class="A")),
        }
        for name, (pairs, call) in fixtures.items():
            snapshot = copy.deepcopy(pairs)
            first = call(pairs).as_dict()
            second = call(pairs).as_dict()
            with self.subTest(fixture=name):
                self.assertEqual(pairs, snapshot)   # input untouched
                self.assertEqual(first, second)      # deterministic

    def test_as_dict_is_json_serialisable(self):
        objects = [
            safe_rate("Accuracy", 2, 3),
            binary_confusion_counts(_binary_pairs(), vocabulary=_VOCAB),
            binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB),
            confusion_matrix(_three_class_pairs(), classes=_CLASSES),
            one_vs_rest_metrics(_three_class_pairs(), classes=_CLASSES, target_class="A"),
            classification_summary(_binary_pairs(), vocabulary=_VOCAB),
            classification_summary(_three_class_pairs(), classes=_CLASSES, target_class="C"),
        ]
        for obj in objects:
            encoded = json.dumps(obj.as_dict(), sort_keys=True)
            self.assertIsInstance(encoded, str)

    def test_pairs_from_rows_preserves_order_and_does_not_mutate(self):
        rows = [{"gt_label": 1, "pred_label": 0}, {"gt_label": None, "pred_label": 1}]
        snapshot = copy.deepcopy(rows)
        lifted = pairs_from_rows(rows, ground_truth_key="gt_label", prediction_key="pred_label")
        self.assertEqual(lifted, ((1, 0), (None, 1)))  # order + None preserved
        self.assertEqual(rows, snapshot)
        # tuple rows work too.
        self.assertEqual(pairs_from_rows([(1, 0), (0, 1)], ground_truth_key="a", prediction_key="b"), ((1, 0), (0, 1)))

    def test_pairs_from_rows_rejects_bad_rows(self):
        with self.assertRaises(IncompatiblePairError):
            pairs_from_rows([5], ground_truth_key="gt", prediction_key="pred")           # int row
        with self.assertRaises(IncompatiblePairError):
            pairs_from_rows([[1, 0, 1]], ground_truth_key="gt", prediction_key="pred")   # 3-item row
        with self.assertRaises(IncompatiblePairError) as ctx:
            pairs_from_rows([{"gt_label": 1}], ground_truth_key="gt_label", prediction_key="pred_label")
        self.assertIn("pred_label", str(ctx.exception))  # missing key is named

    def test_rate_accessor_rejects_unknown_metric(self):
        metrics = binary_classification_metrics(_binary_pairs(), vocabulary=_VOCAB)
        with self.assertRaises(ClassificationError):
            metrics.rate("does-not-exist")
        # The rates mapping preserves the documented seven-metric order.
        self.assertEqual(
            list(metrics.rates),
            ["accuracy", "sensitivity", "specificity", "ppv", "npv", "balanced_accuracy", "predicted_negative_fraction"],
        )
