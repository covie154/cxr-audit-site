# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Structural / strict-parsing tests for the report_v2 definition layer.

These exercise :mod:`report_v2.definitions.loader` -- the strict YAML gatekeeper plus the JSON-Schema
and calendar-date validators -- against the read-only seeds under ``.planning/report-v2`` and a battery
of hand-built malformed documents. They cover every rejection class the YAML contract defines and prove
the loader is side-effect-free.

No database is touched: every test is a :class:`django.test.SimpleTestCase` (or a bare
``unittest`` check) and the production static/SSL/mail configuration is overridden away so the suite is
hermetic.
"""

from __future__ import annotations

import builtins
import inspect
import pathlib
import re
import tempfile
import unittest

from django.test import SimpleTestCase, override_settings

import report_v2
from report_v2.definitions import loader

REPO = pathlib.Path(report_v2.__file__).resolve().parent.parent  # .../cxr-audit-site


def _find_seed_dir():
    # ``.planning`` lives at the repository root (above ``django-app``); walk up the parents until the
    # read-only seed directory is found rather than hard-coding a single ``parent.parent`` hop.
    for candidate in (REPO, *REPO.parents):
        probe = candidate / ".planning" / "report-v2"
        if probe.is_dir():
            return probe
    # Fall back to the conventional location so a missing dir surfaces a clear FileNotFoundError.
    return REPO / ".planning" / "report-v2"


SEED_DIR = _find_seed_dir()
REPORT_SEED = SEED_DIR / "prime-overview.yaml"
POLICY_SEED = SEED_DIR / "lunit-defaults.v1.yaml"
SCHEMAS_DIR = pathlib.Path(loader.__file__).resolve().parent / "schemas"

# Artifacts root routed to a throwaway temp dir so nothing can ever be written into the repo/volume; the
# writes-nothing test asserts this very directory stays empty.
ART_ROOT = tempfile.mkdtemp(prefix="synth-artifacts-")

# A minimal but fully valid REPORT definition used as the mutation base for the schema/date tests.
MIN_REPORT_YAML = """
schema_version: 1
project: prime
id: testreport
title: T
grid:
  columns: 12
  row_height_px: 64
sections:
- id: s
  title: S
  widgets:
  - id: w
    title: W
    type: value
    layout:
      width: 2
      height: 3
    query:
      measurement: record_count
      inputs: {}
    window:
      start: '2025-12-12'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: []
    ci:
      enabled: false
    export: full
"""

_DATE_LIKE = "2026-02-30"  # matches the shape regex yet names a day that never existed.


@override_settings(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUDIT_ARTIFACT_ROOT=ART_ROOT,
)
class DefinitionLoaderTests(SimpleTestCase):
    """Pure, no-database checks over the strict loader, schemas and date gate."""

    # -- seeds --------------------------------------------------------------
    def test_report_seed_parses_and_validates(self):
        text = REPORT_SEED.read_text(encoding="utf-8")
        data = loader.load_report_definition(text, source=str(REPORT_SEED))
        self.assertIsInstance(data, dict)
        self.assertEqual(data["project"], "prime")
        self.assertIn("sections", data)
        self.assertGreaterEqual(len(data["sections"]), 1)
        for section in data["sections"]:
            self.assertIn("widgets", section)
        # Zero structural errors and every calendar date is real.
        self.assertEqual(loader.validate_against_report_schema(data), [])
        self.assertEqual(loader.validate_calendar_dates(data), [])

    def test_policy_seed_parses_and_validates(self):
        text = POLICY_SEED.read_text(encoding="utf-8")
        data = loader.load_policy(text, source=str(POLICY_SEED))
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data["findings"], dict)
        self.assertGreaterEqual(len(data["findings"]), 1)
        self.assertEqual(loader.validate_against_policy_schema(data), [])
        self.assertEqual(loader.validate_calendar_dates(data), [])

    # -- rejection classes --------------------------------------------------
    def test_duplicate_key_block_and_flow_rejected(self):
        with self.assertRaises(loader.DuplicateKeyError):
            loader.parse_strict_yaml("a: 1\na: 2\n")
        with self.assertRaises(loader.DuplicateKeyError):
            loader.parse_strict_yaml("{a: 1, a: 2}")
        err = self._capture(loader.DuplicateKeyError, "x:\n  - {id: w, id: w}\n")
        self.assertIn("x[0]", str(err.path))

    def test_anchor_and_alias_rejected(self):
        with self.assertRaises(loader.AnchorAliasError):
            loader.parse_strict_yaml("a: &node 1\nb: *node\n")

    def test_anchor_only_rejected(self):
        # A defined-but-unused anchor is still an anchor and must be refused.
        with self.assertRaises(loader.AnchorAliasError):
            loader.parse_strict_yaml("a: &unused 1\nb: 2\n")

    def test_merge_key_rejected(self):
        with self.assertRaises(loader.MergeKeyError):
            loader.parse_strict_yaml("k:\n  <<: *base\n")

    def test_unknown_tag_rejected(self):
        with self.assertRaises(loader.UnknownTagError):
            loader.parse_strict_yaml("a: !foo bar\n")
        with self.assertRaises(loader.UnknownTagError):
            loader.parse_strict_yaml("a: !!binary 'aGk='\n")

    def test_multiple_documents_rejected(self):
        with self.assertRaises(loader.MultipleDocumentsError):
            loader.parse_strict_yaml("a: 1\n---\nb: 2\n")

    def test_excessive_size_rejected(self):
        with self.assertRaises(loader.SizeLimitError):
            loader.parse_strict_yaml("a: 1\nb: 2\n", max_bytes=4)

    def test_excessive_depth_rejected(self):
        deep = "[" * 15 + "]" * 15
        with self.assertRaises(loader.DepthLimitError):
            loader.parse_strict_yaml(deep, max_depth=5)

    def test_too_many_nodes_rejected(self):
        many = "".join(f"k{i}: {i}\n" for i in range(50))
        with self.assertRaises(loader.NodeCountLimitError):
            loader.parse_strict_yaml(many, max_nodes=10)

    def test_oversized_scalar_rejected(self):
        with self.assertRaises(loader.ScalarSizeLimitError):
            loader.parse_strict_yaml("a: " + ("x" * 100) + "\n", max_str=20)

    def test_nonfinite_numbers_rejected(self):
        for literal in (".nan", ".inf", "-.inf"):
            with self.assertRaises(loader.NonFiniteNumberError, msg=literal):
                loader.parse_strict_yaml(f"a: {literal}")

    # -- calendar-date semantics -------------------------------------------
    def test_malformed_calendar_date_rejected_semantically(self):
        # Prove the rejection is semantic: the naive shape regex accepts the value, yet the loader
        # still refuses it because the day does not exist.
        self.assertIsNotNone(re.match(r"^\d{4}-\d{2}-\d{2}$", _DATE_LIKE))
        bad = MIN_REPORT_YAML.replace("'2025-12-12'", f"'{_DATE_LIKE}'")
        with self.assertRaises(loader.InvalidCalendarDateError):
            loader.load_report_definition(bad, source="min-report")

    def test_unquoted_malformed_date_rejected(self):
        bad = MIN_REPORT_YAML.replace("'2025-12-12'", _DATE_LIKE)
        with self.assertRaises(loader.InvalidCalendarDateError):
            loader.load_report_definition(bad, source="min-report")

    def test_valid_dates_and_relative_tokens_accepted(self):
        for token in ("2025-12-12", "D", "W", "W-1", "M", "M-1", "Y", "Y-1", "D-7"):
            self.assertEqual(loader.validate_calendar_dates({"start": token, "end": "D"}), [], token)
            # The token survives the round-trip verbatim (valid unquoted dates normalise to their ISO form).
            self.assertEqual(loader.parse_strict_yaml(f"start: {token}"), {"start": token}, token)

    # -- schema (report + policy) ------------------------------------------
    def test_extra_report_key_rejected(self):
        with self.assertRaises(loader.SchemaValidationError) as ctx:
            loader.load_report_definition(MIN_REPORT_YAML + "surprise: 1\n", source="min-report")
        self.assertGreaterEqual(len(ctx.exception.errors), 1)

    def test_missing_required_report_key_rejected(self):
        data = loader.parse_strict_yaml(MIN_REPORT_YAML)
        data.pop("title")
        problems = loader.validate_against_report_schema(data)
        self.assertGreaterEqual(len(problems), 1)
        self.assertTrue(any("title" in p.message for p in problems))

    def test_unknown_policy_key_rejected(self):
        text = POLICY_SEED.read_text(encoding="utf-8") + "\nsurprise: true\n"
        with self.assertRaises(loader.SchemaValidationError):
            loader.load_policy(text, source="policy")

    def test_wrong_type_policy_rejected(self):
        text = POLICY_SEED.read_text(encoding="utf-8").replace("operator: gt", "operator: lt")
        with self.assertRaises(loader.SchemaValidationError):
            loader.load_policy(text, source="policy")

    # -- cross-cutting guarantees ------------------------------------------
    def test_validation_writes_nothing_to_disk(self):
        # Warm every cache and format checker while open() is still normal.
        loader.prewarm_schemas()
        report_data = loader.parse_strict_yaml(REPORT_SEED.read_text(encoding="utf-8"))
        policy_data = loader.parse_strict_yaml(POLICY_SEED.read_text(encoding="utf-8"))
        loader.validate_against_report_schema(report_data)
        loader.validate_against_policy_schema(policy_data)

        opened = []
        real_open = builtins.open

        def spy_open(file, *args, **kwargs):
            mode = str(args[0] if args else kwargs.get("mode", "r"))
            opened.append(mode)
            return real_open(file, *args, **kwargs)

        bad_docs = [
            "a: 1\na: 2\n",
            "a: &x 1\n",
            "a: !foo bar\n",
            "a: .nan",
            "a: 1\n---\nb: 2\n",
        ]
        builtins.open = spy_open
        try:
            for text in bad_docs:
                with self.assertRaises(loader.DefinitionError):
                    loader.parse_strict_yaml(text, source="bad")
            self.assertEqual(loader.validate_against_report_schema(report_data), [])
            self.assertEqual(loader.validate_against_policy_schema(policy_data), [])
            self.assertEqual(loader.validate_calendar_dates(report_data), [])
        finally:
            builtins.open = real_open

        write_like = [mode for mode in opened if set(mode) & set("wax+")]
        self.assertEqual(write_like, [], f"unexpected write-mode opens: {write_like}")
        self.assertEqual(list(pathlib.Path(ART_ROOT).iterdir()), [])

    def test_editor_messages_are_path_aware(self):
        deep = (
            "sections:\n"
            "- id: s\n"
            "  title: S\n"
            "  widgets:\n"
            "  - id: w\n"
            "    id: w2\n"
        )
        err = self._capture(loader.DuplicateKeyError, deep)
        self.assertIn("sections[0].widgets[", str(err.path))
        self.assertIsNotNone(err.line)
        self.assertIsNotNone(err.column)
        payload = err.as_editor_dict()
        self.assertEqual(
            sorted(payload),
            sorted(["source", "path", "line", "column", "kind", "message"]),
        )

    def test_no_executable_template_evaluation(self):
        data = loader.parse_strict_yaml(
            "a: '{__class__.__init__}'\n"
            "b: '{{ 7*7 }}'\n"
            "c: \"os.system('id')\"\n"
        )
        self.assertEqual(data["a"], "{__class__.__init__}")
        self.assertEqual(data["b"], "{{ 7*7 }}")
        self.assertEqual(data["c"], "os.system('id')")

        source = inspect.getsource(loader)
        for token in (
            "eval", "exec", "compile", "subprocess", "os.system", "os.popen", "Template", "format_map",
        ):
            self.assertNotIn(token, source, f"forbidden token present in loader: {token!r}")

    def test_schema_files_are_packaged(self):
        for name, expected_id in (
            ("report.schema.json", "urn:primer:report-definition:1"),
            ("policy.schema.json", "urn:primer:threshold-policy:1"),
        ):
            path = SCHEMAS_DIR / name
            self.assertTrue(path.is_file(), str(path))
            schema = loader.load_schema(name)
            self.assertIsInstance(schema, dict)
            self.assertEqual(schema["$id"], expected_id)

    # -- helpers ------------------------------------------------------------
    def _capture(self, exc_type, text, **limits):
        try:
            loader.parse_strict_yaml(text, **limits)
        except exc_type as exc:
            return exc
        self.fail(f"expected {exc_type.__name__} for {text!r}")
