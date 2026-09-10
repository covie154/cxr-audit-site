# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused, database-free coverage for the report-v2 threshold / prediction layer.

These exercise the pure computation entry points in :mod:`report_v2.measurements.predictions`: the explicit
strict ``gt`` binarisation, the ``any_positive`` aggregate under the ``require_all_scores`` policy, the
label pass-through path, and every typed validation guard. They pin the runbook's DONE-WHEN guarantees and the
"Threshold versioning" hand-check block:

* a score exactly equal to its threshold is *not* positive (strict greater-than, never greater-or-equal);
* a score strictly above its threshold is positive;
* a missing required constituent makes the aggregate **ineligible** (``label`` / ``positive`` are ``None``),
  never silently coerced to the negative class;
* identical scores across two synthetic sites produce identical labels (there is no site-specific branch);
* a policy's version 1 and version 2 coexist without one overwriting the other or mutating stored state.

No database, ORM, factories or real/clinical data are touched: the whole suite is
:class:`django.test.SimpleTestCase`, the synthetic project is built from the generic ``base`` dataclasses, and
PRIME is exercised only through the read-only production registry / a throwaway registry -- never the writable
production singleton. The production static / SSL / mail configuration is overridden away so the suite is
hermetic.
"""

from __future__ import annotations

import math

from django.test import SimpleTestCase, override_settings

from report_v2.measurements import predictions as predictions_module
from report_v2.measurements.predictions import (
    LabelPredictionResult,
    NonFiniteScoreError,
    OutOfVocabularyLabelError,
    PredictionResult,
    ScoreOutOfRangeError,
    UncoveredFindingError,
    classify_label_prediction,
    classify_prediction,
    resolve_policy,
)
from report_v2.projects import base, prime, registry

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

# The ten PRIME binarised findings carried by the production ``lunit-defaults`` policy (nodule defaults to 15,
# the other nine to 10). Spelled out here so the production integration tests build complete findings mappings.
_PRIME_FINDINGS = (
    "atelectasis",
    "calcification",
    "cardiomegaly",
    "consolidation",
    "fibrosis",
    "mediastinal_widening",
    "nodule",
    "pleural_effusion",
    "pneumoperitoneum",
    "pneumothorax",
)


def _hand_v1_policy() -> base.ThresholdPolicy:
    """Version 1 of the synthetic two-finding hand-check policy (both thresholds 10.0)."""
    return base.ThresholdPolicy(
        policy_id="hand-thresholds",
        version=1,
        score_scale=(0.0, 100.0),
        operator="gt",
        aggregate="any_positive",
        require_all_scores=True,
        findings={"consolidation": 10.0, "nodule": 10.0},
    )


def _hand_v2_policy() -> base.ThresholdPolicy:
    """Version 2 of the hand-check policy (thresholds 12.0), modelled as a distinct coexisting entry.

    The generic catalog keys ``policies`` by ``policy_id`` and stores exactly one :class:`ThresholdPolicy` per
    key (and ``ProjectDefinition.policy('id@version')`` checks ``policy.version == version``). To let version 1
    and version 2 *coexist* without one overwriting the other, they are registered under two distinct,
    immutable keys -- ``hand-thresholds``@1 and ``hand-thresholds-v2``@2. Neither entry is ever replaced.
    """
    return base.ThresholdPolicy(
        policy_id="hand-thresholds-v2",
        version=2,
        score_scale=(0.0, 100.0),
        operator="gt",
        aggregate="any_positive",
        require_all_scores=True,
        findings={"consolidation": 12.0, "nodule": 12.0},
    )


def _hand_outcome() -> base.Outcome:
    return base.Outcome("abnormal_hand", ("normal", "abnormal"), "abnormal", meaning="Hand-check abnormality")


def _build_hand_project() -> base.ProjectDefinition:
    """The synthetic two-finding project used by every threshold hand-check.

    Its prediction path needs only the policy + outcome; ``sources`` / ``measurements`` are left empty because
    ``classify_prediction`` reads ``policy.findings`` (not the source declarations) to bin scores.
    """
    policies = {
        p.policy_id: p
        for p in (_hand_v1_policy(), _hand_v2_policy())
    }
    return base.ProjectDefinition(
        project_id="handth",
        display_name="Synthetic hand-check project",
        timezone="UTC",
        model_label="demo.handmodel",
        sources={},
        outcomes={o.outcome_id: o for o in (_hand_outcome(),)},
        cohorts={},
        dimensions={},
        policies=policies,
        measurements={},
    )


def _build_policyless_project() -> base.ProjectDefinition:
    """A project with an outcome but NO registered policies, proving label pass-through needs no policy."""
    return base.ProjectDefinition(
        project_id="nopolicy",
        display_name="Synthetic policy-less project",
        timezone="UTC",
        model_label="demo.nomodel",
        outcomes={o.outcome_id: o for o in (_hand_outcome(),)},
    )


def _mixed_registry() -> registry.ProjectRegistry:
    """A throwaway registry holding BOTH PRIME and the hand project (never a production singleton)."""
    reg = registry.ProjectRegistry()
    reg.register(prime.PROJECT)
    reg.register(_build_hand_project(), allow_overwrite=True)
    return reg


def _complete_prime_findings(**overrides) -> dict:
    """A complete, in-range mapping over all ten PRIME findings (baseline 5.0) with optional overrides."""
    scores = {finding: 5.0 for finding in _PRIME_FINDINGS}
    scores.update(overrides)
    return scores


@override_settings(**_SETTINGS_OVERRIDES)
class ThresholdPredictionTests(SimpleTestCase):
    """The five DONE-WHEN guarantees and the runbook hand-check block."""

    def test_score_equal_to_threshold_is_negative(self):
        reg = _mixed_registry()
        result = classify_prediction(
            {"consolidation": 10.0, "nodule": 10.0},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        self.assertIsInstance(result, PredictionResult)
        self.assertTrue(result.eligible)
        self.assertFalse(result.positive)
        self.assertEqual(result.label, "normal")
        self.assertFalse(result.findings["consolidation"].positive)  # 10 is NOT > 10
        self.assertFalse(result.findings["nodule"].positive)

    def test_score_above_threshold_is_positive(self):
        reg = _mixed_registry()
        result = classify_prediction(
            {"consolidation": 11.0, "nodule": 10.0},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        self.assertTrue(result.eligible)
        self.assertTrue(result.positive)
        self.assertEqual(result.label, "abnormal")
        self.assertTrue(result.findings["consolidation"].positive)  # 11 > 10
        self.assertFalse(result.findings["nodule"].positive)  # 10 !> 10

    def test_missing_constituent_makes_aggregate_ineligible_not_negative(self):
        reg = _mixed_registry()
        result = classify_prediction(
            {"consolidation": 11.0, "nodule": None},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        self.assertFalse(result.eligible)
        self.assertIsNone(result.label)  # NOT the negative label
        self.assertIsNone(result.positive)
        self.assertEqual(result.missing_findings, ("nodule",))
        self.assertIn("nodule", result.reason)

    def test_identical_scores_across_two_sites_produce_identical_labels(self):
        reg = _mixed_registry()
        findings = {"consolidation": 11.0, "nodule": 10.0}
        # The site code is a label only; classify_prediction has no site-specific branch and ignores it.
        row_a = dict(findings, _site="SYNTH-SITE-A")
        row_b = dict(findings, _site="SYNTH-SITE-B")
        # Strip the non-policy site marker before classifying (the policy does not cover it).
        result_a = classify_prediction(
            {k: v for k, v in row_a.items() if k in ("consolidation", "nodule")},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        result_b = classify_prediction(
            {k: v for k, v in row_b.items() if k in ("consolidation", "nodule")},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        self.assertEqual((result_a.label, result_a.positive), (result_b.label, result_b.positive))
        self.assertEqual(
            {fid: dec.positive for fid, dec in result_a.findings.items()},
            {fid: dec.positive for fid, dec in result_b.findings.items()},
        )

    def test_policy_version_one_and_two_coexist_without_overwrite(self):
        reg = _mixed_registry()
        v1 = resolve_policy("handth", "hand-thresholds@1", registry=reg)
        v2 = resolve_policy("handth", "hand-thresholds-v2@2", registry=reg)
        before_v1 = dict(v1.findings)
        before_v2 = dict(v2.findings)

        pos_v1 = classify_prediction(
            {"consolidation": 11.0, "nodule": 10.0},
            project_id="handth",
            policy_ref="hand-thresholds@1",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        pos_v2 = classify_prediction(
            {"consolidation": 11.0, "nodule": 10.0},
            project_id="handth",
            policy_ref="hand-thresholds-v2@2",
            registry=reg,
            outcome_id="abnormal_hand",
        )
        self.assertTrue(pos_v1.positive)  # 11 > 10
        self.assertFalse(pos_v2.positive)  # 11 !> 12
        self.assertEqual(pos_v2.label, "normal")

        # The two policy objects' findings mappings are unchanged after both evaluations.
        self.assertEqual(dict(v1.findings), before_v1)
        self.assertEqual(dict(v2.findings), before_v2)
        # Resolving v1 again still yields its own (threshold 10) reference, version attrs differ.
        again = resolve_policy("handth", "hand-thresholds@1", registry=reg)
        self.assertEqual(again.findings["consolidation"], 10.0)
        self.assertEqual(v1.version, 1)
        self.assertEqual(v2.version, 2)

    def test_hand_check_threshold_block(self):
        reg = _mixed_registry()

        def run(findings, ref="hand-thresholds@1"):
            return classify_prediction(
                findings, project_id="handth", policy_ref=ref, registry=reg, outcome_id="abnormal_hand"
            )

        neg = run({"consolidation": 10.0, "nodule": 10.0})
        self.assertFalse(neg.positive)
        self.assertEqual(neg.label, "normal")
        self.assertTrue(neg.eligible)

        pos = run({"consolidation": 11.0, "nodule": 10.0})
        self.assertTrue(pos.positive)
        self.assertEqual(pos.label, "abnormal")
        self.assertTrue(pos.eligible)

        inelig = run({"consolidation": 11.0, "nodule": None})
        self.assertFalse(inelig.eligible)
        self.assertIsNone(inelig.label)
        self.assertIsNone(inelig.positive)
        self.assertEqual(inelig.missing_findings, ("nodule",))

        v2neg = run({"consolidation": 11.0, "nodule": 10.0}, ref="hand-thresholds-v2@2")
        self.assertFalse(v2neg.positive)
        self.assertEqual(v2neg.label, "normal")

        # identical rows across two sites keep equal labels (no site branch in the path).
        self.assertEqual(run({"consolidation": 11.0, "nodule": 10.0}).label,
                         run({"consolidation": 11.0, "nodule": 10.0}).label)

    def test_gt_is_strict_not_ge(self):
        reg = _mixed_registry()

        def consolidation_positive(score):
            result = classify_prediction(
                {"consolidation": score, "nodule": 10.0},
                project_id="handth",
                policy_ref="hand-thresholds@1",
                registry=reg,
                outcome_id="abnormal_hand",
            )
            return result.findings["consolidation"].positive

        self.assertFalse(consolidation_positive(10.0))  # 10 !> 10  (not >=)
        self.assertTrue(consolidation_positive(10.000001))  # strictly greater


@override_settings(**_SETTINGS_OVERRIDES)
class ValidationGuardTests(SimpleTestCase):
    """Every typed guard rejects malformed configuration / input without any silent fallback."""

    def test_unknown_policy_raises_typed_error_no_fallback(self):
        reg = _mixed_registry()
        with self.assertRaises(base.UnknownPolicyError):
            resolve_policy("handth", "does-not-exist@1", registry=reg)
        with self.assertRaises(base.UnknownPolicyError):
            classify_prediction(
                {"consolidation": 11.0, "nodule": 10.0},
                project_id="handth",
                policy_ref="does-not-exist@1",
                registry=reg,
                outcome_id="abnormal_hand",
            )

    def test_foreign_policy_raises_cross_project_error(self):
        reg = _mixed_registry()
        # PRIME's own policy requested from the hand project context -> owner is exactly one other project.
        with self.assertRaises(base.CrossProjectReferenceError) as ctx:
            resolve_policy("handth", "lunit-defaults@1", registry=reg)
        message = str(ctx.exception)
        self.assertIn("handth", message)
        self.assertIn("prime", message)
        # The hand project's own policy requested from the PRIME context.
        with self.assertRaises(base.CrossProjectReferenceError):
            resolve_policy("prime", "hand-thresholds@1", registry=reg)

    def test_unknown_project_raises(self):
        reg = _mixed_registry()
        with self.assertRaises(base.UnknownProjectError):
            resolve_policy("no-such-project", "hand-thresholds@1", registry=reg)

    def test_out_of_range_score_rejected(self):
        reg = _mixed_registry()
        for value in (101.0, -0.1):
            with self.subTest(value=value):
                with self.assertRaises(ScoreOutOfRangeError) as ctx:
                    classify_prediction(
                        {"consolidation": value, "nodule": 10.0},
                        project_id="handth",
                        policy_ref="hand-thresholds@1",
                        registry=reg,
                        outcome_id="abnormal_hand",
                    )
                self.assertIn("consolidation", str(ctx.exception))

    def test_nonfinite_score_rejected(self):
        reg = _mixed_registry()
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(NonFiniteScoreError):
                    classify_prediction(
                        {"consolidation": value, "nodule": 10.0},
                        project_id="handth",
                        policy_ref="hand-thresholds@1",
                        registry=reg,
                        outcome_id="abnormal_hand",
                    )

    def test_uncovered_finding_rejected(self):
        reg = _mixed_registry()
        with self.assertRaises(UncoveredFindingError) as ctx:
            classify_prediction(
                {"consolidation": 10.0, "nodule": 10.0, "tuberculosis": 50.0},
                project_id="handth",
                policy_ref="hand-thresholds@1",
                registry=reg,
                outcome_id="abnormal_hand",
            )
        self.assertIn("tuberculosis", str(ctx.exception))

    def test_bool_is_not_accepted_as_score(self):
        reg = _mixed_registry()
        with self.assertRaises(ScoreOutOfRangeError):
            classify_prediction(
                {"consolidation": True, "nodule": 10.0},
                project_id="handth",
                policy_ref="hand-thresholds@1",
                registry=reg,
                outcome_id="abnormal_hand",
            )


@override_settings(**_SETTINGS_OVERRIDES)
class LabelPassThroughTests(SimpleTestCase):
    """Label-valued sources pass straight through to an outcome vocabulary (no thresholding)."""

    def test_out_of_vocabulary_label_rejected(self):
        reg = _mixed_registry()
        with self.assertRaises(OutOfVocabularyLabelError):
            classify_label_prediction(
                "sometimes", project_id="handth", outcome_id="abnormal_hand", registry=reg
            )

    def test_label_passthrough_no_thresholding(self):
        reg = _mixed_registry()
        pos = classify_label_prediction("abnormal", project_id="handth", outcome_id="abnormal_hand", registry=reg)
        self.assertIsInstance(pos, LabelPredictionResult)
        self.assertTrue(pos.eligible)
        self.assertTrue(pos.positive)
        self.assertEqual(pos.label, "abnormal")
        self.assertFalse(hasattr(pos, "policy_ref"))  # label results carry no policy reference / numeric score

        neg = classify_label_prediction("normal", project_id="handth", outcome_id="abnormal_hand", registry=reg)
        self.assertFalse(neg.positive)
        self.assertEqual(neg.label, "normal")

        # A project WITHOUT any registered policy still classifies a label (no policy lookup happens).
        solo = registry.ProjectRegistry()
        solo.register(_build_policyless_project(), allow_overwrite=True)
        result = classify_label_prediction(
            "abnormal", project_id="nopolicy", outcome_id="abnormal_hand", registry=solo
        )
        self.assertTrue(result.eligible)
        self.assertTrue(result.positive)

    def test_label_passthrough_missing_value(self):
        reg = _mixed_registry()
        result = classify_label_prediction(None, project_id="handth", outcome_id="abnormal_hand", registry=reg)
        self.assertFalse(result.eligible)
        self.assertIsNone(result.label)
        self.assertIsNone(result.positive)


@override_settings(**_SETTINGS_OVERRIDES)
class PrimeIntegrationTests(SimpleTestCase):
    """The production PRIME path (registry=None) binarises the full ten-finding policy coherently."""

    def test_primes_policy_resolves_from_production_registry(self):
        policy = resolve_policy("prime", "lunit-defaults@1")  # registry=None -> production singleton
        self.assertIs(policy, prime.PROJECT.policy("lunit-defaults@1"))

        negative = classify_prediction(_complete_prime_findings(), project_id="prime", policy_ref="lunit-defaults@1")
        self.assertFalse(negative.positive)
        self.assertEqual(negative.label, "normal")
        self.assertTrue(negative.eligible)

        nodule_high = classify_prediction(
            _complete_prime_findings(nodule=20.0), project_id="prime", policy_ref="lunit-defaults@1"
        )
        self.assertTrue(nodule_high.positive)  # 20 > 15
        self.assertEqual(nodule_high.label, "abnormal")

        # Equality at the higher (nodule 15) threshold is still negative under the strict gt operator.
        nodule_equal = classify_prediction(
            _complete_prime_findings(nodule=15.0), project_id="prime", policy_ref="lunit-defaults@1"
        )
        self.assertFalse(nodule_equal.positive)  # 15 !> 15
        self.assertFalse(nodule_equal.findings["nodule"].positive)
        self.assertEqual(nodule_equal.label, "normal")

        atelectasis_high = classify_prediction(
            _complete_prime_findings(atelectasis=11.0), project_id="prime", policy_ref="lunit-defaults@1"
        )
        self.assertTrue(atelectasis_high.positive)  # 11 > 10

        atelectasis_equal = classify_prediction(
            _complete_prime_findings(atelectasis=10.0), project_id="prime", policy_ref="lunit-defaults@1"
        )
        self.assertFalse(atelectasis_equal.positive)  # 10 !> 10
        self.assertEqual(atelectasis_equal.label, "normal")

    def test_primes_missing_any_of_ten_findings_is_ineligible(self):
        findings = _complete_prime_findings()
        del findings["nodule"]
        result = classify_prediction(findings, project_id="prime", policy_ref="lunit-defaults@1")
        self.assertFalse(result.eligible)
        self.assertIsNone(result.label)
        self.assertIsNone(result.positive)
        self.assertIn("nodule", result.missing_findings)

    def test_pure_computation_no_orm_no_mutation(self):
        policy = resolve_policy("prime", "lunit-defaults@1")
        snapshot = dict(policy.findings)

        findings = _complete_prime_findings(nodule=20.0)
        findings_copy = dict(findings)
        for _ in range(3):
            classify_prediction(findings, project_id="prime", policy_ref="lunit-defaults@1")

        # (a) the resolved immutable policy was not mutated.
        self.assertEqual(dict(policy.findings), snapshot)
        # (b) the caller's findings mapping was not mutated.
        self.assertEqual(findings, findings_copy)
        # (c) the module is pure: no ORM / model symbols leaked into its globals.
        self.assertNotIn("CXrStudy", predictions_module.__dict__)
        self.assertNotIn("models", predictions_module.__dict__)
        self.assertNotIn("django", predictions_module.__dict__)
        self.assertNotIn("upload", predictions_module.__dict__)
