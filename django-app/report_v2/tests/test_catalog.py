# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused coverage for the report-v2 project catalog, its registries and the access boundary.

These exercise the generic metadata model (:mod:`report_v2.projects.base`), the configured PRIME adapter
(:mod:`report_v2.projects.prime`), the production / test-only registries and the require-project-context
guard (:mod:`report_v2.projects.registry`), and the permission predicates (:mod:`report_v2.permissions`).
They prove the four guarantees the runbook pins for this task:

* unknown project / source / outcome / cohort / dimension / policy / measurement identifiers fail loudly and
  the unknown-project lookup never silently falls back to PRIME;
* reaching another registered project's identifier from a context raises the cross-project error while a
  legitimate in-project lookup still succeeds;
* the generic definition model and the strict parser are free of any clinical field vocabulary;
* the edit rule is the shared ``admins``-group-or-superuser predicate and the view rule is a plain login gate.

No database is contacted: every test is a :class:`django.test.SimpleTestCase` and the production static /
SSL / mail configuration is overridden away so the suite is hermetic.
"""

from __future__ import annotations

import dataclasses
import inspect

from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, override_settings

from report_v2 import permissions
from report_v2.definitions import loader
from report_v2.projects import base, prime, registry

# Tokens that must never leak into the *generic* definition model or the strict parser (they belong only in
# the adapter-owned PRIME catalog). Checked case-insensitively against the module source text.
_FORBIDDEN_GENERIC_TOKENS = (
    "workplace", "gt_llm", "gt_manual", "lunit", "nodule", "atelectasis", "calcification",
    "cardiomegaly", "consolidation", "fibrosis", "mediastinal", "pleural", "pneumoperitoneum",
    "pneumothorax", "tuberculosis", "abnormal", "accession", "text_report", "time_to_clinical",
    "time_end_to_end",
)

_SETTINGS_OVERRIDES = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)


def _build_synthetic_project() -> base.ProjectDefinition:
    """Build the second, purely synthetic project used to exercise the cross-project guard.

    Its metadata is intentionally generic and fictional (``x_``-prefixed identifiers, a fake ``x_score`` /
    ``x_site`` pair) so that it proves the guard works structurally without encoding any clinical field. It
    is *only* ever reachable through the test-only / explicit registries, never through production navigation.
    """
    sources = {
        s.source_id: s
        for s in (
            base.Source("x_value", "score", "x_score", unit="0-100"),
            base.Source("x_site", "identifier", "x_site"),
        )
    }
    outcomes = {o.outcome_id: o for o in (base.Outcome("x_binary", ("neg", "pos"), "pos"),)}
    cohorts = {c.cohort_id: c for c in (base.Cohort("x_open", description="Everything, unrestricted."),)}
    dimensions = {d.dimension_id: d for d in (base.Dimension("x_site", "x_site", label="Site"),)}
    policies = {
        p.policy_id: p
        for p in (
            base.ThresholdPolicy(
                policy_id="x-defaults",
                version=1,
                score_scale=(0.0, 100.0),
                operator="gt",
                aggregate="any_positive",
                require_all_scores=True,
                findings={"x_score": 10.0},
            ),
        )
    }
    measurements = {m.measurement_id: m for m in (base.MeasurementSignature("x_measure", inputs={"value": "score"}),)}
    return base.ProjectDefinition(
        project_id="synthx",
        display_name="Synthetic demo project",
        timezone="UTC",
        model_label="demo.syntheticmodel",
        sources=sources,
        outcomes=outcomes,
        cohorts=cohorts,
        dimensions=dimensions,
        policies=policies,
        measurements=measurements,
    )


def _register_synthetic_project(target: registry.ProjectRegistry) -> base.ProjectDefinition:
    """Register the synthetic project into ``target`` (a caller-supplied, test-side registry)."""
    definition = _build_synthetic_project()
    target.register(definition, allow_overwrite=True)
    return definition


def _mixed_registry() -> registry.ProjectRegistry:
    """A throwaway registry holding BOTH PRIME and the synthetic project (never a production singleton)."""
    reg = registry.ProjectRegistry()
    reg.register(prime.PROJECT)
    _register_synthetic_project(reg)
    return reg


@override_settings(**_SETTINGS_OVERRIDES)
class CatalogLookupTests(SimpleTestCase):
    """Strict, no-fallback lookups and the cross-project guard."""

    def test_primes_definition_is_the_configured_project(self):
        self.assertIs(prime.get_project_definition(), prime.PROJECT)
        self.assertEqual(prime.PROJECT.project_id, "prime")
        self.assertEqual(prime.PROJECT.model_label, "upload.cxrstudy")

    def test_unknown_project_raises_and_does_not_fall_back_to_prime(self):
        with self.assertRaises(base.UnknownProjectError):
            registry.require_project_context("definitely-not-a-project")
        # The unknown lookup returned no value at all (the assertRaises above proves it), and separately
        # prove PRIME really is present while the bogus id is not -- i.e. there was nothing to fall back to.
        self.assertIsNone(registry.production_registry().get("definitely-not-a-project"))
        self.assertIsNotNone(registry.production_registry().get("prime"))
        # A genuine request resolves to the real, validated context (identity with the singleton's PROJECT).
        self.assertIs(registry.require_project_context("prime"), prime.PROJECT)

    def test_unknown_identifiers_raise_their_specific_typed_errors(self):
        for kwargs, exc in (
            ({"source_id": "no_such_source"}, base.UnknownSourceError),
            ({"outcome_id": "no_such_outcome"}, base.UnknownOutcomeError),
            ({"cohort_id": "no_such_cohort"}, base.UnknownCohortError),
            ({"dimension_id": "no_such_dimension"}, base.UnknownDimensionError),
            ({"measurement_id": "no_such_measurement"}, base.UnknownMeasurementError),
            ({"policy_ref": "no-such-policy@1"}, base.UnknownPolicyError),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(exc):
                    registry.require_project_context("prime", **kwargs)

    def test_malformed_policy_references_are_rejected(self):
        # Directly against the definition AND through the require guard; both reject the same shapes.
        for bad in ("id@", "@3", "id@x"):
            with self.subTest(ref=bad):
                with self.assertRaises(base.UnknownPolicyError):
                    prime.PROJECT.policy(bad)
                with self.assertRaises(base.UnknownPolicyError):
                    registry.require_project_context("prime", policy_ref=bad)

    def test_foreign_identifier_raises_cross_project_error(self):
        reg = _mixed_registry()
        with self.assertRaises(base.CrossProjectReferenceError) as ctx:
            registry.require_project_context("prime", registry=reg, source_id="x_value")
        message = str(ctx.exception)
        self.assertIn("prime", message)
        self.assertIn("synthx", message)

    def test_in_project_lookups_still_succeed_once_guarded(self):
        reg = _mixed_registry()
        # "site" is genuinely PRIME's own source; "x_value" is genuinely synthx's own source.
        self.assertIs(registry.require_project_context("prime", registry=reg, source_id="site"), prime.PROJECT)
        self.assertIs(registry.require_project_context("synthx", registry=reg, source_id="x_value"), reg.get("synthx"))

    def test_registering_test_project_never_touches_production(self):
        before = registry.production_registry().ids()
        definition = _build_synthetic_project()
        registry.register_test_project(definition)
        after = registry.production_registry().ids()
        self.assertEqual(before, after)
        self.assertIsNone(registry.production_registry().get("synthx"))
        self.assertIsNotNone(registry.production_registry().get("prime"))
        # ... while the isolated test registry *did* receive it and can resolve it.
        self.assertIsNotNone(registry.test_registry().get("synthx"))

    def test_require_test_project_context_reaches_the_test_project(self):
        registry.register_test_project(_build_synthetic_project())
        resolved = registry.require_test_project_context("synthx", source_id="x_value", measurement_id="x_measure")
        self.assertEqual(resolved.project_id, "synthx")
        with self.assertRaises(base.UnknownProjectError):
            registry.require_test_project_context("prime")


@override_settings(**_SETTINGS_OVERRIDES)
class PrimeMetadataConsistencyTests(SimpleTestCase):
    """The PRIME catalog matches the reviewed read-only seeds and the CXRStudy field names."""

    def test_referenced_sources_have_expected_kinds(self):
        project = prime.get_project_definition()
        cases = {
            "record_id": "record_id",
            "site": "identifier",
            "procedure_date": "timestamp",
            "report_text": "text",
            "manual_abnormal": "label",
            "llm_abnormal": "label",
            "lunit_binarised": "label",
            "time_to_clinical_decision": "duration",
            "time_end_to_end": "duration",
            "score_nodule": "score",
        }
        for source_id, kind in cases.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(project.source(source_id).kind, kind)
        self.assertEqual(project.source("time_end_to_end").unit, "seconds")
        self.assertEqual(project.source("time_to_clinical_decision").unit, "seconds")
        self.assertEqual(project.source("score_nodule").unit, "0-100")

    def test_policy_mirrors_lunit_defaults_seed(self):
        policy = prime.get_project_definition().policy("lunit-defaults@1")
        self.assertEqual(policy.policy_id, "lunit-defaults")
        self.assertEqual(policy.version, 1)
        self.assertEqual(policy.ref, "lunit-defaults@1")
        self.assertEqual(policy.operator, "gt")
        self.assertEqual(policy.aggregate, "any_positive")
        self.assertTrue(policy.require_all_scores)
        self.assertEqual(tuple(policy.score_scale), (0.0, 100.0))
        self.assertEqual(policy.findings["nodule"], 15)
        for finding, threshold in policy.findings.items():
            with self.subTest(finding=finding):
                expected = 15 if finding == "nodule" else 10
                self.assertEqual(threshold, expected)

    def test_policy_bare_reference_resolves_and_cross_context_policy_resolves(self):
        # A bare id names the single registered version; it must equal the qualified reference.
        project = prime.get_project_definition()
        self.assertIs(project.policy("lunit-defaults"), project.policy("lunit-defaults@1"))
        self.assertIs(registry.require_project_context("prime", policy_ref="lunit-defaults@1"), project)

    def test_outcomes_use_the_declared_binary_vocabulary(self):
        project = prime.get_project_definition()
        for outcome_id in ("abnormal_manual", "abnormal_llm", "abnormal_lunit"):
            with self.subTest(outcome_id=outcome_id):
                outcome = project.outcome(outcome_id)
                self.assertEqual(tuple(outcome.classes), ("normal", "abnormal"))
                self.assertEqual(outcome.positive_class, "abnormal")

    def test_cohorts_and_dimension_are_as_specified(self):
        project = prime.get_project_definition()
        manual = project.cohort("manual_label_present")
        self.assertEqual(dict(manual.predicate), {"gt_manual__isnull": False})
        self.assertEqual(manual.requires_fields, ("gt_manual",))
        self.assertEqual(dict(project.cohort("all").predicate), {})
        site = project.dimension("site")
        self.assertEqual(site.field, "workplace")
        self.assertEqual(site.allowed_values, ("SYNTH-SITE-A", "SYNTH-SITE-B"))

    def test_measurement_signatures_are_as_specified(self):
        project = prime.get_project_definition()
        record = project.measurement("record_count")
        self.assertEqual(dict(record.inputs), {})
        self.assertTrue(record.supports_comparison)
        self.assertEqual(dict(record.units), {"value": "count"})
        for metric in ("accuracy", "sensitivity", "specificity", "balanced_accuracy"):
            with self.subTest(metric=metric):
                sig = project.measurement(metric)
                self.assertEqual(dict(sig.inputs), {"ground_truth": "label", "prediction": "label"})
                self.assertTrue(sig.requires_threshold_policy)
        agreement = project.measurement("reference_agreement")
        self.assertEqual(dict(agreement.units), {"agreement": "ratio", "kappa": "ratio"})


@override_settings(**_SETTINGS_OVERRIDES)
class ImmutableDataclassTests(SimpleTestCase):
    """The value objects are frozen and self-validating."""

    def test_mutating_a_frozen_instance_raises(self):
        source = prime.get_project_definition().source("record_id")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            source.field = "tampered"

    def test_outcome_rejects_positive_class_outside_vocabulary(self):
        with self.assertRaises(ValueError):
            base.Outcome("bad", ("normal", "abnormal"), "sometimes")

    def test_source_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            base.Source("bad", "mystery-kind", "col")

    def test_policy_rejects_bad_operator_and_zero_version(self):
        with self.assertRaises(ValueError):
            base.ThresholdPolicy("p", 1, (0.0, 100.0), "ge", "any_positive", True, {"f": 10.0})
        with self.assertRaises(ValueError):
            base.ThresholdPolicy("p", 0, (0.0, 100.0), "gt", "any_positive", True, {"f": 10.0})


@override_settings(**_SETTINGS_OVERRIDES)
class ParserPurityTests(SimpleTestCase):
    """No clinical field vocabulary may appear in the generic model or the strict parser."""

    def test_generic_model_and_parser_are_field_vocabulary_free(self):
        for label, module in (("base", base), ("loader", loader)):
            source_text = inspect.getsource(module).lower()
            for token in _FORBIDDEN_GENERIC_TOKENS:
                with self.subTest(module=label, token=token):
                    self.assertNotIn(token, source_text)


@override_settings(**_SETTINGS_OVERRIDES)
class PermissionTests(SimpleTestCase):
    """Edit uses the shared admin rule; view is a plain login gate."""

    @staticmethod
    def _user(*, is_superuser: bool, in_admins: bool):
        user = Mock(is_superuser=is_superuser)
        user.groups.filter.return_value.exists.return_value = in_admins
        return user

    def test_can_edit_catalog_mirrors_the_admin_rule(self):
        self.assertTrue(permissions.can_edit_catalog(self._user(is_superuser=True, in_admins=False)))
        self.assertTrue(permissions.can_edit_catalog(self._user(is_superuser=False, in_admins=True)))
        self.assertFalse(permissions.can_edit_catalog(self._user(is_superuser=False, in_admins=False)))

    def test_admin_required_decorator_gate(self):
        # In this Django build ``user_passes_test`` grants by running the view and denies by redirecting to
        # the login page (it reuses ``redirect_to_login``), never by raising. So a rejected request must send
        # the client to ``/login/?next=`` and must NOT run the protected body.
        sentinel = "granted"
        calls = {"body": 0}

        @permissions.admin_required
        def _view(request):  # exercised directly, mirroring how the house decorator is applied to views.
            calls["body"] += 1
            return sentinel

        request = RequestFactory().get("/report/")
        request.user = self._user(is_superuser=True, in_admins=False)
        self.assertEqual(_view(request), sentinel)
        request.user = self._user(is_superuser=False, in_admins=True)
        self.assertEqual(_view(request), sentinel)
        self.assertEqual(calls["body"], 2)  # the body ran for the two permitted users only

        request.user = self._user(is_superuser=False, in_admins=False)
        response = _view(request)
        self.assertEqual(calls["body"], 2)  # rejected: the protected body did not run
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=", response.url)

    def test_view_gate_requires_authentication(self):
        self.assertTrue(permissions.can_view_published(Mock(is_authenticated=True)))
        self.assertFalse(permissions.can_view_published(Mock(is_authenticated=False)))

    def test_published_report_only_redirects_anonymous(self):
        @permissions.published_report_only
        def _protected(request):
            return "secret"

        request = RequestFactory().get("/report/")
        request.user = AnonymousUser()
        response = _protected(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=", response.url)

    def test_published_report_only_allows_authenticated(self):
        @permissions.published_report_only
        def _protected(request):
            return "secret"

        request = RequestFactory().get("/report/")
        request.user = Mock(is_authenticated=True, is_superuser=False)
        request.user.groups.filter.return_value.exists.return_value = False
        self.assertEqual(_protected(request), "secret")
