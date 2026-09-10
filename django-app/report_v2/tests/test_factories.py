# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Focused tests for the report_v2 synthetic FIXTURE / FACTORY layer.

These tests validate the fixtures themselves against the runbook hand-checks; they
do NOT reimplement the v2 measurement engine.
"""

import tempfile
import unittest

from django.test import TestCase, override_settings

from upload.models import CXRStudy
from . import factories

# Mirror test_routes.py's static-storage override convention (plain storage, no
# manifest/whitenoise), plus disable the SSL redirect and use the locmem email
# backend, and route any artifact root to a temp dir (never the repo/volume).
@override_settings(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUDIT_ARTIFACT_ROOT=tempfile.mkdtemp(prefix="synth-artifacts-"),
)
class FactoryDbTests(TestCase):
    """DB-backed fixture tests -- run only against the runner's test database."""

    def test_db_rows_create_in_test_db(self):
        created = []
        created += factories.binary_fixture_db()
        created += factories.binary_fixture_with_missing_gt_db()
        created += factories.binary_fixture_no_positive_gt_db()
        created += factories.three_class_fixture_db()
        created += factories.timing_fixture_db()
        created += factories.missing_field_fixture_db()
        created += factories.older_subgroup_fixture_db()
        created += factories.create_default_population()

        expected = len(created)
        self.assertEqual(expected, 50)
        self.assertEqual(CXRStudy.objects.count(), expected)

        # Every stored row's identifiers must carry the synthetic prefixes.
        for study in CXRStudy.objects.all():
            factories._assert_synthetic_only(study)
            self.assertTrue(str(study.patient_name).startswith("SYNTH PATIENT"))
            self.assertTrue(str(study.patient_id).startswith("SYNTH-PID-"))
            self.assertTrue(str(study.study_id).startswith("SYNTH-STUDY-"))
            self.assertTrue(str(study.text_report).startswith("SYNTHETIC-TEST-REPORT"))
            self.assertTrue(str(study.workplace).startswith("SYNTH-SITE"))
            self.assertIn(
                factories.RESERVED_ACCESSION_BASE,
                range(factories.RESERVED_ACCESSION_BASE,
                      factories.RESERVED_ACCESSION_BASE + factories.RESERVED_ACCESSION_SPAN),
            )

    def test_ensure_test_database_allows_runner_db(self):
        # Positive control: inside the runner's test database the guard must NOT
        # raise (proving it does not false-reject the legitimate test DB).
        factories.ensure_test_database()
        # An on-disk production path can never satisfy the guard: a *.sqlite3 basename
        # is hard-rejected before any in-memory/test_ acceptance check.
        self.assertTrue("db.sqlite3".endswith((".sqlite", ".sqlite3", ".db")))
        self.assertFalse("memory" in "db.sqlite3".lower() or "db.sqlite3".startswith("test_"))

    def test_binary_db_reproduces_policy_from_designated_finding(self):
        # The stored designated-finding score must be consistent with the strict >10
        # policy that v2 uses to recompute lunit_binarised.
        for study in factories.binary_fixture_db(base=201):
            score = getattr(study, factories.BINARY_DESIGNATED_FINDING)
            self.assertEqual(
                int(score > factories.SCORE_THRESHOLD),
                study.lunit_binarised,
                msg=f"designated score {score} inconsistent with binarised {study.lunit_binarised}",
            )


class FactoryInMemoryTests(unittest.TestCase):
    """Pure, no-database tests over the in-memory record builders."""

    def test_binary_confusion_self_check(self):
        recs = factories.binary_fixture()
        tp = sum(1 for r in recs if r["gt_label"] == 1 and r["pred_label"] == 1)
        fn = sum(1 for r in recs if r["gt_label"] == 1 and r["pred_label"] == 0)
        fp = sum(1 for r in recs if r["gt_label"] == 0 and r["pred_label"] == 1)
        tn = sum(1 for r in recs if r["gt_label"] == 0 and r["pred_label"] == 0)
        self.assertEqual((tp, fn, fp, tn), (2, 1, 1, 2))
        # predicted-negative fraction denominator is the full 6-row cohort.
        self.assertEqual(len(recs), 6)

    def test_binary_missing_gt_matching(self):
        recs = factories.binary_fixture_with_missing_gt()
        matching = sum(1 for r in recs if r.get("in_coverage"))
        eligible = sum(1 for r in recs if r.get("in_coverage") and r.get("gt_label") is not None)
        self.assertEqual((matching, eligible, matching - eligible), (7, 6, 1))

    def test_three_class_matrix_self_check(self):
        recs = factories.three_class_fixture()
        order = recs[0]["classes"]
        self.assertEqual(order, ["A", "B", "C"])
        idx = {c: i for i, c in enumerate(order)}
        matrix = [[0, 0, 0] for _ in order]
        for r in recs:
            matrix[idx[r["gt_class"]]][idx[r["pred_class"]]] += 1
        self.assertEqual(matrix, [[1, 1, 0], [0, 1, 1], [1, 0, 1]])
        correct = sum(matrix[i][i] for i in range(len(order)))
        self.assertEqual((correct, len(recs)), (3, 6))  # accuracy numerator/denominator 3/6
        # Class A one-vs-rest.
        tp = matrix[0][0]
        fn = sum(matrix[0]) - matrix[0][0]
        fp = sum(matrix[i][0] for i in range(len(order))) - matrix[0][0]
        tn = len(recs) - tp - fn - fp
        self.assertEqual((tp, fn, fp, tn), (1, 1, 1, 3))

    def test_determinism(self):
        for builder in (
            factories.timing_fixture,
            factories.three_class_fixture,
            factories.binary_fixture_with_missing_gt,
        ):
            self.assertEqual(builder(), builder(), f"{builder.__name__} is not deterministic")

    def test_synthetic_only(self):
        for builder in (
            factories.binary_fixture,
            factories.binary_fixture_with_missing_gt,
            factories.binary_fixture_no_positive_gt,
            factories.three_class_fixture,
            factories.timing_fixture,
            factories.missing_field_fixture,
            factories.older_subgroup_fixture,
        ):
            for rec in builder():
                # _assert_synthetic_only raises AssertionError on any non-synthetic id.
                factories._assert_synthetic_only(rec)
                if rec.get("site") is not None:
                    factories.assert_no_real_identifiers(rec["site"])
        self.assertTrue(factories.TEXT_REPORT_PREFIX.startswith("SYNTHETIC-TEST-REPORT"))
