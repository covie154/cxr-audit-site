# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused, database-free coverage for the report-v2 reference-comparison measurement layer.

These exercise the pure inter-rater entry points in :mod:`report_v2.measurements.agreement`:
Cohen's kappa, McNemar's marginal-homogeneity test and the false-negative / false-positive case
listing. The whole suite is pinned against the reference-comparison guarantees:

* perfect agreement yields a kappa of exactly ``1.0`` (a defined rate, ``null_reason`` unset);
* an *undefined* kappa -- degenerate marginals (a single class on either side, so the expected
  agreement is ``1``) or an empty complete population -- yields ``value is None`` carrying a
  non-empty ``null_reason`` and is **never** ``0`` / ``0.0``; a genuine zero kappa over a
  positive denominator stays a *defined* ``0.0``, so the suite proves the two states distinct;
* McNemar's discordants follow the fixed direction -- ``b`` is reference-positive &
  prediction-negative, ``c`` is reference-negative & prediction-positive -- and the test is
  *two-sided*: the exact binomial p-value is reported (with a continuity-corrected chi-square
  alongside) and the method is documented on the result;
* McNemar and kappa are computed over the SAME common-complete-row filter: incomplete pairs (a
  missing / off-vocabulary side, or a bool) are excluded consistently by both entry points, and
  that shared ``n_complete`` is asserted rather than assumed;
* the FN / FP direction is fixed (``manual`` is the reference, ``llm`` the prediction): a false
  negative is reference-positive & prediction-negative, a false positive reference-negative &
  prediction-positive -- swapping them is a bug the suite catches -- and the two id lists page
  SEPARATELY from each other and from the aggregate counts.

No database, ORM, real/clinical data or the reference snapshot are touched: the whole suite is
:class:`django.test.SimpleTestCase`, the populations are plain synthetic value lists plus the
synthetic in-memory ``factories`` (``binary_fixture`` and friends), and PRIME is read only through
the frozen catalog. The production static / SSL / mail configuration is overridden away so the
suite is hermetic.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re

from django.test import SimpleTestCase, override_settings

from report_v2.measurements import agreement as agreement_module
from report_v2.measurements.agreement import (
    AgreementError,
    Rate,
    cohen_kappa,
    complete_rows,
    fn_fp_cases,
    mcnemar,
)
from report_v2.tests.factories import (
    RESERVED_ACCESSION_BASE,
    RESERVED_ACCESSION_SPAN,
    binary_fixture,
    binary_fixture_no_positive_gt,
    binary_fixture_with_missing_gt,
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# The runbook binary block: manual/GT [1,1,1,0,0,0] versus llm/prediction [1,1,0,1,0,0].
_REF = [1, 1, 1, 0, 0, 0]
_PRED = [1, 1, 0, 1, 0, 0]


def _reference_two_sided_p(b, c):
    """Independent restatement of the documented exact two-sided binomial McNemar p-value."""
    n = b + c
    k = min(b, c)
    tail = sum(math.comb(n, j) * 0.5 ** n for j in range(k + 1))
    return min(1.0, 2.0 * tail)


def _columns(rows):
    refs = [row["gt_label"] for row in rows]
    preds = [row["pred_label"] for row in rows]
    ids = [row["accession"] for row in rows]
    return refs, preds, ids


# ---------------------------------------------------------------------------
# A. Cohen's kappa: perfect, defined, and the null-plus-reason contract.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class CohenKappaTests(SimpleTestCase):
    """Kappa is a :class:`Rate`: perfect is ``1.0``, undefined is ``None`` plus a reason."""

    def test_perfect_agreement_is_exactly_one(self):
        labels = [1, 1, 0, 0, 1, 0]
        result = cohen_kappa(labels, list(labels))
        self.assertIsInstance(result, Rate)
        self.assertTrue(result.defined)
        self.assertIsNone(result.null_reason)
        self.assertEqual(result.value, 1.0)
        self.assertEqual(result.numerator, result.denominator)

    def test_undefined_is_never_zero(self):
        # The historical bug this suite exists to prevent: reporting 0 for an undefined ratio.
        degenerate_cases = (
            ([1, 1, 1, 1], [1, 1, 1, 1]),     # single class on both sides -> expected agreement 1
            ([0, 0, 0], [0, 0, 0]),            # single class on both sides
            ([None, 1, None, 1], [None, 1, None, 1]),  # complete subset is single-class
            ([], []),                             # empty population
            ([None, None], [1, 0]),              # nothing completes
        )
        for refs, preds in degenerate_cases:
            result = cohen_kappa(refs, preds)
            with self.subTest(msg=f"{refs} vs {preds}"):
                self.assertIsNone(result.value)
                self.assertFalse(result.defined)
                self.assertIsNot(result.value, 0)
                self.assertIsNot(result.value, 0.0)
                self.assertIsInstance(result.null_reason, str)
                self.assertTrue(result.null_reason.strip())

    def test_all_negative_column_is_undefined_not_zero(self):
        result = cohen_kappa([0, 0, 0], [0, 0, 0])
        self.assertIsNone(result.value)
        self.assertTrue(result.null_reason.strip())

    def test_empty_population_is_undefined_with_a_reason(self):
        result = cohen_kappa([], [])
        self.assertIsNone(result.value)
        self.assertIn("empty", result.null_reason.lower())

    def test_genuine_zero_kappa_stays_defined(self):
        # po == pe here, so kappa is a real 0.0 over a positive denominator -- distinct from None.
        result = cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])
        self.assertTrue(result.defined)
        self.assertEqual(result.value, 0.0)
        self.assertIsNone(result.null_reason)
        self.assertGreater(result.denominator, 0)

    def test_undefined_and_genuine_zero_are_distinct_states(self):
        undefined = cohen_kappa([1, 1, 1, 1], [1, 1, 1, 1])
        genuine_zero = cohen_kappa([1, 1, 0, 0], [1, 0, 1, 0])
        self.assertIsNone(undefined.value)
        self.assertEqual(genuine_zero.value, 0.0)
        self.assertIsNotNone(genuine_zero.value)
        self.assertIsNotNone(undefined.null_reason)
        self.assertIsNone(genuine_zero.null_reason)

    def test_documented_binary_block_kappa_value(self):
        # po = 4/6, pe = 0.5 -> kappa = (4/6 - 1/2) / (1 - 1/2).
        result = cohen_kappa(_REF, _PRED)
        self.assertTrue(result.defined)
        self.assertEqual(result.numerator, 4)
        self.assertEqual(result.denominator, 6)
        self.assertAlmostEqual(result.value, (4 / 6 - 1 / 2) / (1 - 1 / 2))

    def test_chance_level_agreement_is_a_defined_negative_value(self):
        # Anti-correlated labelling is a real measurement (kappa -1.0), not a null.
        result = cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1])
        self.assertTrue(result.defined)
        self.assertEqual(result.value, -1.0)

    def test_rate_is_frozen_and_round_trips(self):
        self.assertTrue(dataclasses.is_dataclass(Rate))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cohen_kappa(_REF, _PRED).value = 0.5
        snap = dataclasses.asdict(cohen_kappa(_REF, _PRED))
        self.assertEqual(set(snap), {"label", "numerator", "denominator", "value", "null_reason"})
        json.dumps(snap)

    def test_rate_rejects_a_defined_value_paired_with_a_reason(self):
        # The null-plus-reason contract is structural: a defined rate must not smuggle a reason.
        with self.assertRaises(AgreementError):
            Rate(label="broken", value=0.5, null_reason="should not be here")
        with self.assertRaises(AgreementError):
            Rate(label="broken", value=None, null_reason="   ")

    def test_undefined_rate_requires_a_non_empty_reason(self):
        result = cohen_kappa([], [])
        self.assertIsNone(result.value)
        self.assertTrue(result.null_reason.strip())
        with self.assertRaises(AgreementError):
            Rate(label="broken", value=None, null_reason=None)

    def test_incomplete_rows_are_dropped_before_kappa(self):
        refs = [1, 1, 1, 0, 0, 0, None, "x", True]
        preds = [1, 1, 0, 1, 0, 0, 1, 0, 0]
        result = cohen_kappa(refs, preds)
        # Only the first six pairs are complete, so the denominator is 6, not 9.
        self.assertEqual(result.denominator, 6)
        self.assertEqual(result.numerator, 4)
        self.assertAlmostEqual(result.value, (4 / 6 - 1 / 2) / (1 - 1 / 2))

    def test_ragged_inputs_are_rejected(self):
        with self.assertRaises(AgreementError):
            cohen_kappa([1, 0, 1], [1, 0])


# ---------------------------------------------------------------------------
# B. McNemar: discordants, the two-sided statistic and the shared filter.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class McNemarTests(SimpleTestCase):
    """``b`` = ref-pos/pred-neg, ``c`` = ref-neg/pred-pos; the test is two-sided."""

    def test_binary_block_discordant_counts(self):
        result = mcnemar(_REF, _PRED)
        # One (1,0) pair and one (0,1) pair in the runbook block.
        self.assertEqual(result.b, 1)
        self.assertEqual(result.c, 1)
        self.assertEqual(result.n_discordant, 2)
        self.assertEqual(result.n_total, 6)
        self.assertEqual(result.n_complete, 6)
        self.assertEqual(result.excluded_incomplete, 0)

    def test_discordant_direction_is_not_swappable(self):
        refs = [1, 1, 1, 1, 0]
        preds = [0, 0, 0, 1, 0]
        result = mcnemar(refs, preds)
        self.assertEqual(result.b, 3)   # three reference-positive / prediction-negative pairs
        self.assertEqual(result.c, 0)   # no reference-negative / prediction-positive pair
        flipped = mcnemar(preds, refs)  # swapping the roles moves them to the other cell
        self.assertEqual(flipped.b, 0)
        self.assertEqual(flipped.c, 3)

    def test_two_sided_p_value_is_symmetric_in_b_and_c(self):
        left = mcnemar([1, 1, 1, 1, 0], [0, 0, 0, 1, 0])
        right = mcnemar([0, 0, 0, 1, 0], [1, 1, 1, 1, 0])
        self.assertEqual((left.b, left.c), (3, 0))
        self.assertEqual((right.b, right.c), (0, 3))
        self.assertAlmostEqual(left.p_value, right.p_value)

    def test_p_value_matches_the_independent_reference_restatement(self):
        cases = (
            ([1, 1, 1, 1, 0], [0, 0, 0, 1, 0]),          # b=3, c=0
            ([1] * 12 + [0], [0] * 12 + [1]),               # b=12, c=1
            (_REF, _PRED),                                    # b=1, c=1 (clips to 1.0)
            ([1, 1, 0, 0], [0, 0, 1, 1]),                    # b=2, c=2
        )
        for refs, preds in cases:
            result = mcnemar(refs, preds)
            with self.subTest(msg=f"b={result.b} c={result.c}"):
                self.assertAlmostEqual(
                    result.p_value, _reference_two_sided_p(result.b, result.c), places=12
                )

    def test_p_value_is_a_probability(self):
        for refs, preds in (
            ([1] * 20, [0] * 20),
            ([1, 0, 1, 0], [0, 1, 0, 1]),
            ([1, 1, 0, 0], [0, 0, 1, 1]),
            ([1, 1, 1, 0], [1, 1, 1, 0]),
        ):
            result = mcnemar(refs, preds)
            if result.p_value is not None:
                with self.subTest(msg=str(result.p_value)):
                    self.assertGreaterEqual(result.p_value, 0.0)
                    self.assertLessEqual(result.p_value, 1.0)

    def test_continuity_corrected_chi_square_statistic(self):
        result = mcnemar([1] * 12 + [0], [0] * 12 + [1])    # b=12, c=1
        self.assertEqual((result.b, result.c), (12, 1))
        self.assertEqual(result.n_discordant, 13)
        self.assertAlmostEqual(result.statistic, (abs(12 - 1) - 1) ** 2 / 13.0)
        self.assertLess(result.p_value, 0.05)                  # a strong asymmetry is significant

    def test_method_string_documents_the_statistic(self):
        result = mcnemar(_REF, _PRED)
        lowered = result.method.lower()
        self.assertIn("two-sided", lowered)
        self.assertIn("binomial", lowered)
        self.assertIn("mcnemar", lowered)

    def test_perfect_concordance_has_no_discordants_and_no_numbers(self):
        result = mcnemar([1, 1, 0, 0], [1, 1, 0, 0])
        self.assertEqual(result.n_discordant, 0)
        self.assertIsNone(result.statistic)
        self.assertIsNone(result.p_value)
        self.assertTrue(result.p_note.strip())                  # a reason is stated, not a fabricated 0

    def test_empty_population_carries_no_numbers(self):
        result = mcnemar([], [])
        self.assertEqual(result.n_total, 0)
        self.assertEqual(result.n_complete, 0)
        self.assertEqual(result.n_discordant, 0)
        self.assertIsNone(result.statistic)
        self.assertIsNone(result.p_value)
        self.assertTrue(result.p_note.strip())

    def test_kappa_and_mcnemar_share_one_complete_row_filter(self):
        # The same incomplete rows must fall out of BOTH entry points identically.
        refs = [1, 1, 1, 0, 0, 0, None, "x", True]
        preds = [1, 1, 0, 1, 0, 0, 1, 0, 0]
        kappa = cohen_kappa(refs, preds)
        result = mcnemar(refs, preds)
        self.assertEqual(result.n_complete, 6)
        self.assertEqual(kappa.denominator, result.n_complete)
        self.assertEqual(result.n_total, 9)
        self.assertEqual(result.excluded_incomplete, 3)
        self.assertEqual(result.n_complete + result.excluded_incomplete, result.n_total)

    def test_incomplete_rows_never_masquerade_as_a_class(self):
        # A missing reference must not be read as a negative (which would inflate ``c``).
        clean = mcnemar(_REF, _PRED)
        padded = mcnemar([None] + _REF, [0] + _PRED)
        self.assertEqual(padded.b, clean.b)
        self.assertEqual(padded.c, clean.c)
        self.assertEqual(padded.excluded_incomplete, 1)
        self.assertEqual(padded.n_complete, clean.n_complete)

    def test_complete_rows_is_the_shared_filter_primitive(self):
        rows = complete_rows([1, None, True, "x", 0], [1, 0, 0, 1, 5], ["a", "b", "c", "d", "e"])
        self.assertEqual(rows.total, 5)
        self.assertEqual(rows.complete, 1)
        self.assertEqual(rows.excluded_incomplete, 4)
        self.assertEqual(rows.ref, (1,))
        self.assertEqual(rows.pred, (1,))
        self.assertEqual(rows.ids, ("a",))

    def test_complete_rows_rejects_ragged_inputs(self):
        with self.assertRaises(AgreementError):
            complete_rows([1, 0], [1, 0, 1])
        with self.assertRaises(AgreementError):
            complete_rows([1, 0], [1, 0], ["only-one"])

    def test_result_is_frozen(self):
        result = mcnemar(_REF, _PRED)
        self.assertTrue(dataclasses.is_dataclass(result))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.b = 99


# ---------------------------------------------------------------------------
# C. FN / FP case lists: fixed direction and separate pagination.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class FNFPCaseTests(SimpleTestCase):
    """Manual is the reference, llm the prediction; the two id lists page independently."""

    @staticmethod
    def _ids(count):
        return [RESERVED_ACCESSION_BASE + 900 + i for i in range(count)]

    def test_binary_block_case_lists(self):
        ids = self._ids(6)
        result = fn_fp_cases(_REF, _PRED, ids)
        # FN = reference-positive & prediction-negative -> the third case only.
        self.assertEqual(result.false_negative_ids, (ids[2],))
        # FP = reference-negative & prediction-positive -> the fourth case only.
        self.assertEqual(result.false_positive_ids, (ids[3],))
        self.assertEqual(result.false_negative_count, 1)
        self.assertEqual(result.false_positive_count, 1)
        self.assertEqual(result.n_total, 6)
        self.assertEqual(result.n_complete, 6)

    def test_direction_is_manual_reference_and_llm_prediction(self):
        result = fn_fp_cases(_REF, _PRED, self._ids(6), reference="manual", prediction="llm")
        self.assertEqual(result.reference, "manual")
        self.assertEqual(result.prediction, "llm")

    def test_every_listed_case_carries_the_documented_orientation(self):
        refs = [1, 1, 1, 0, 0, 0]
        preds = [1, 1, 0, 1, 0, 0]
        ids = self._ids(6)
        result = fn_fp_cases(refs, preds, ids)
        by_id = dict(zip(ids, zip(refs, preds)))
        for ident in result.false_negative_ids:
            self.assertEqual(by_id[ident], (1, 0))       # reference positive, prediction negative
        for ident in result.false_positive_ids:
            self.assertEqual(by_id[ident], (0, 1))       # reference negative, prediction positive

    def test_swapping_the_direction_names_is_rejected(self):
        with self.assertRaises(AgreementError):
            fn_fp_cases([1, 0], [0, 1], ["a", "b"], reference="llm", prediction="manual")

    def test_unknown_direction_names_are_rejected(self):
        with self.assertRaises(AgreementError):
            fn_fp_cases([1, 0], [1, 0], ["a", "b"], reference="clinician", prediction="llm")
        with self.assertRaises(AgreementError):
            fn_fp_cases([1, 0], [1, 0], ["a", "b"], reference="manual", prediction="manual")

    def test_the_two_lists_paginate_separately(self):
        refs = [1] * 5 + [0] * 5
        preds = [0] * 5 + [1] * 5
        ids = self._ids(10)
        result = fn_fp_cases(refs, preds, ids, fn_offset=2, fn_limit=2, fp_offset=1, fp_limit=1)
        # Five FN ids (indices 0..4) and five FP ids (indices 5..9) with INDEPENDENT windows.
        self.assertEqual(result.false_negative_ids_view, (ids[2], ids[3]))
        self.assertEqual(result.false_positive_ids_view, (ids[6],))
        # The canonical lists and the aggregates are untouched by either window.
        self.assertEqual(result.false_negative_ids, tuple(ids[0:5]))
        self.assertEqual(result.false_positive_ids, tuple(ids[5:10]))
        self.assertEqual(result.false_negative_count, 5)
        self.assertEqual(result.false_positive_count, 5)
        self.assertEqual(result.n_complete, 10)

    def test_re_paging_one_list_leaves_the_other_alone(self):
        base = fn_fp_cases([1] * 4 + [0] * 4, [0] * 4 + [1] * 4, self._ids(8))
        self.assertEqual(base.false_negative_ids_view, base.false_negative_ids)
        repaged = base.with_paging(fp_offset=2, fp_limit=1)
        # The FP list is ids[4..7]; the window [2:3] selects the third FP id.
        self.assertEqual(repaged.false_positive_ids_view, (RESERVED_ACCESSION_BASE + 906,))
        # The FN window was not requested, so it is still the full range.
        self.assertEqual(len(repaged.false_negative_ids_view), 4)

    def test_pagination_never_truncates_the_aggregates(self):
        ids = self._ids(6)
        result = fn_fp_cases(_REF, _PRED, ids, fn_offset=0, fn_limit=0, fp_offset=99, fp_limit=10)
        self.assertEqual(result.false_negative_ids_view, ())
        self.assertEqual(result.false_positive_ids_view, ())
        # The aggregate counts survive any window: paging is a view, not a filter of the truth.
        self.assertEqual(result.false_negative_count, 1)
        self.assertEqual(result.false_positive_count, 1)
        self.assertEqual(result.false_negative_ids, (ids[2],))
        self.assertEqual(result.false_positive_ids, (ids[3],))

    def test_incomplete_pairs_are_excluded_and_counted_not_labelled(self):
        # A missing prediction on a reference-positive row is neither an FN nor an FP: it is excluded.
        refs = [1, 1, 1, 0]
        preds = [0, None, 0, 1]
        ids = ["id-0", "id-1", "id-2", "id-3"]
        result = fn_fp_cases(refs, preds, ids)
        self.assertEqual(result.false_negative_ids, ("id-0", "id-2"))
        self.assertEqual(result.false_positive_ids, ("id-3",))
        self.assertEqual(result.excluded_incomplete, 1)
        self.assertEqual(result.n_complete, 3)
        self.assertEqual(result.n_complete + result.excluded_incomplete, 4)
        self.assertNotIn("id-1", result.false_negative_ids)
        self.assertNotIn("id-1", result.false_positive_ids)

    def test_a_bool_label_is_incomplete_not_a_zero_or_one(self):
        # ``True`` must not be read as the positive label and ``False`` as the negative one.
        result = fn_fp_cases([True, False], [False, True], ["t", "f"])
        self.assertEqual(result.false_negative_ids, ())
        self.assertEqual(result.false_positive_ids, ())
        self.assertEqual(result.excluded_incomplete, 2)
        self.assertEqual(result.n_complete, 0)

    def test_result_is_frozen(self):
        result = fn_fp_cases(_REF, _PRED, self._ids(6))
        self.assertTrue(dataclasses.is_dataclass(result))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.false_negative_count = 0

    def test_ragged_inputs_are_rejected(self):
        with self.assertRaises(AgreementError):
            fn_fp_cases([1, 0], [1, 0, 1], ["a", "b", "c"])
        with self.assertRaises(AgreementError):
            fn_fp_cases([1, 0], [1, 0], ["a", "b", "c"])


# ---------------------------------------------------------------------------
# D. The synthetic binary factories drive the agreement layer end to end.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class FactoryAgreementTests(SimpleTestCase):
    """``binary_fixture`` rows reproduce the runbook comparison, synthetic-only."""

    def test_fixture_rows_stay_inside_the_reserved_synthetic_block(self):
        for row in binary_fixture():
            self.assertGreaterEqual(row["accession"], RESERVED_ACCESSION_BASE)
            self.assertLess(row["accession"], RESERVED_ACCESSION_BASE + RESERVED_ACCESSION_SPAN)

    def test_fixture_kappa_matches_the_hand_computation(self):
        refs, preds, _ = _columns(binary_fixture())
        result = cohen_kappa(refs, preds)
        self.assertTrue(result.defined)
        self.assertAlmostEqual(result.value, (4 / 6 - 1 / 2) / (1 - 1 / 2))

    def test_fixture_no_positive_reference_kappa_is_a_defined_zero_not_null(self):
        # The single-class *reference* column is not degenerate by itself: the prediction still
        # mixes classes, so the expected agreement is 0.5 and kappa is a *measured* 0.0.
        # It must be a defined zero, never smuggled into the undefined/null state.
        refs, preds, _ = _columns(binary_fixture_no_positive_gt())
        self.assertEqual(set(refs), {0})
        self.assertEqual(set(preds), {0, 1})          # prediction still spans both classes
        result = cohen_kappa(refs, preds)
        self.assertTrue(result.defined)
        self.assertIsNotNone(result.value)
        self.assertEqual(result.value, 0.0)
        self.assertIsNone(result.null_reason)
        self.assertGreater(result.denominator, 0)

    def test_truly_degenerate_single_class_column_is_null_never_zero(self):
        # The genuine undefined edge (both sides one class, so the expected agreement is 1): the
        # null-plus-reason contract applies and it is NEVER reported as the 0.0 measured above.
        result = cohen_kappa([0, 0, 0, 0], [0, 0, 0, 0])
        self.assertIsNone(result.value)
        self.assertFalse(result.defined)
        self.assertIsNot(result.value, 0)
        self.assertIsNot(result.value, 0.0)
        self.assertTrue(result.null_reason.strip())

    def test_fixture_missing_reference_row_is_excluded_consistently(self):
        # The extra row has no ground truth: kappa and McNemar must drop it identically.
        refs, preds, _ = _columns(binary_fixture_with_missing_gt())
        kappa = cohen_kappa(refs, preds)
        result = mcnemar(refs, preds)
        self.assertEqual(kappa.denominator, 6)
        self.assertEqual(result.n_complete, 6)
        self.assertEqual(result.n_total, 7)
        self.assertEqual(result.excluded_incomplete, 1)

    def test_fixture_case_lists_are_not_swapped(self):
        refs, preds, ids = _columns(binary_fixture())
        result = fn_fp_cases(refs, preds, ids)
        self.assertEqual(result.false_negative_ids, (ids[2],))
        self.assertEqual(result.false_positive_ids, (ids[3],))
        rows_by_id = {row["accession"]: row for row in binary_fixture()}
        for accession in result.false_negative_ids:
            row = rows_by_id[accession]
            self.assertEqual((row["gt_label"], row["pred_label"]), (1, 0))
        for accession in result.false_positive_ids:
            row = rows_by_id[accession]
            self.assertEqual((row["gt_label"], row["pred_label"]), (0, 1))

    def test_fixture_mcnemar_reproduces_the_runbook_discordants(self):
        refs, preds, _ = _columns(binary_fixture())
        result = mcnemar(refs, preds)
        self.assertEqual(result.b, 1)
        self.assertEqual(result.c, 1)
        self.assertEqual(result.n_discordant, 2)


# ---------------------------------------------------------------------------
# E. Purity guards.
# ---------------------------------------------------------------------------
@override_settings(**_SETTINGS_OVERRIDES)
class PurityTests(SimpleTestCase):
    """The module is a pure value layer: stdlib only, no ORM, no threshold machinery."""

    def test_module_imports_no_orm_db_or_network_layer(self):
        with open(agreement_module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        imported = re.findall(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)", source, re.MULTILINE)
        roots = {name.split(".")[0] for name in imported}
        for forbidden in ("django", "upload", "models", "sqlite3", "requests", "urllib"):
            self.assertNotIn(forbidden, roots)
        self.assertIn("dataclasses", roots)
        self.assertIn("fractions", roots)

    def test_no_threshold_or_score_ranking_capability_leaks_in(self):
        # Task 08 measures agreement only; sweeping / ranking belongs elsewhere.
        for name in vars(agreement_module):
            lowered = name.lower()
            for banned in ("threshold", "roc", "auc", "macro_average"):
                self.assertNotIn(banned, lowered)

    def test_helpers_do_not_mutate_their_inputs(self):
        refs, preds, ids = list(_REF), list(_PRED), [1, 2, 3, 4, 5, 6]
        snapshot = (list(refs), list(preds), list(ids))
        cohen_kappa(refs, preds)
        mcnemar(refs, preds)
        fn_fp_cases(refs, preds, ids)
        self.assertEqual((refs, preds, ids), snapshot)

    def test_every_entry_point_returns_a_value_object_or_scalar(self):
        self.assertIsInstance(cohen_kappa(_REF, _PRED), Rate)
        self.assertTrue(dataclasses.is_dataclass(mcnemar(_REF, _PRED)))
        self.assertTrue(dataclasses.is_dataclass(fn_fp_cases(_REF, _PRED, [1, 2, 3, 4, 5, 6])))
