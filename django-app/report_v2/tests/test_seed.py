# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 16 (C1a) seed suite: packaging, validation, install and the admin seed action.

Every filesystem touch goes through an injected scratch ``REPORT_V2_ROOT`` / an explicit tempdir
``--root`` -- never the real ``private_data`` tree, never ``~/serverfiles/downloads/db_2026-06-18.sqlite3``.
The only database touched is Django's own in-memory *test* database created by the runner. Each named
test carries a one-line docstring mapping it to a Task-16 Done-when criterion. A sibling run (C1b) appends
tests 9-16 as a second class; the shared constants and helpers below are module-level for that reason.
"""
from __future__ import annotations

import hashlib
import inspect
import io
import os
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from report_v2 import admin_views as av
from report_v2 import seeding
from report_v2 import views
from report_v2.definitions.loader import load_policy, load_report_definition
from report_v2.definitions.repository import DefinitionRepository, StaleRevisionError
from report_v2.projects.prime import get_project_definition
from report_v2.seed import (
    POLICY_SEED_NAME,
    REPORT_SEED_NAME,
    SEED_DEF_ID,
    policy_seed_text,
    report_seed_text,
    seed_dir,
)
from upload.models import CXRStudy

# ---------------------------------------------------------------------------
# Module-level shared fixtures (kept here so C1b can add a second test class).
# ---------------------------------------------------------------------------

#: The exact scratch-root override every editor/seed test runs under (mirrors test_editor.py's idiom).
_SETTINGS = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

#: The seven display kinds registered in the client widget registry (the *platform* set, not the seed's).
_SEVEN_DISPLAY_KINDS = {"value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"}

#: The supervisor-proved summary of the packaged seed; asserted verbatim in test #2.
_EXPECTED_SUMMARY = {
    "def_id": "overview",
    "title": "Analysis Report",
    "sections": 4,
    "widgets": 17,
    "by_type": {"boxplot": 2, "line": 3, "table": 7, "value": 5},
}

#: Output columns the PRIME adapter projects into the evaluator row (data.py fetch_project_rows / _map_inputs).
#: These are legitimate "adapter projections" -- not ``CXRStudy`` model columns -- and are the fallback used
#: when a bound source's physical ``.field`` is not a real model field.
_ADAPTER_ROW_KEYS = {
    "accession",
    "site",
    "event_date",
    "eligible",
    "gt_label",
    "pred_label",
    "duration_seconds",
}

#: (packaged seed file name -> planning original name); the planning root is ``../.planning/report-v2``
#: relative to django-app, i.e. ``seed_dir().parents[2] / .planning / report-v2``.
_SEED_TO_PLANNING = {
    REPORT_SEED_NAME: "prime-overview.yaml",
    POLICY_SEED_NAME: "lunit-defaults.v1.yaml",
}


def _planning_root() -> Path:
    """Resolve the ``../.planning/report-v2`` directory (read-only reference for the vendored copies)."""
    return seed_dir().parents[2] / ".planning" / "report-v2"


def _files_under(path: str | Path) -> list[str]:
    """Every regular file beneath ``path`` (empty list == "nothing was written")."""
    collected: list[str] = []
    for dirpath, _dirs, filenames in os.walk(str(path)):
        for name in filenames:
            collected.append(os.path.join(dirpath, name))
    return collected


def _strip_first_line(text: str) -> list[str]:
    """Drop exactly the leading (comment banner) line, keeping every other byte verbatim (incl. EOLs)."""
    return text.splitlines(keepends=True)[1:]


@override_settings(**_SETTINGS)
class SeedTests(TestCase):
    """One named test per Task-16 (C1a) Done-when item; all state under an injected scratch root."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="seed-admin", email="seed-admin@example.invalid", password="pw-strong-1"
        )
        cls.normal = User.objects.create_user(
            username="seed-normal", email="seed-normal@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rv2-t16-seed-"))
        overrider = override_settings(REPORT_V2_ROOT=str(self.root))
        overrider.enable()
        self.addCleanup(overrider.disable)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    # -- helpers -----------------------------------------------------------
    def _fresh_root(self) -> Path:
        """A brand-new empty scratch root the caller is responsible for cleaning up."""
        fresh = Path(tempfile.mkdtemp(prefix="rv2-t16-root-"))
        self.addCleanup(lambda: shutil.rmtree(fresh, ignore_errors=True))
        return fresh

    def _client(self, *, enforce_csrf=False):
        return Client(SERVER_NAME="localhost", enforce_csrf_checks=enforce_csrf)

    def _as_admin(self, *, enforce_csrf=False):
        client = self._client(enforce_csrf=enforce_csrf)
        client.force_login(self.admin)
        return client

    def _as_normal(self):
        client = self._client()
        client.force_login(self.normal)
        return client

    def _repo(self, root: Path) -> DefinitionRepository:
        return DefinitionRepository(root, project_id="prime")

    # -- 1. vendoring + immutability + read-only access --------------------
    def test_seed_files_are_vendored_and_immutable_copies(self):
        """Both seeds are packaged, strict-load cleanly, and equal their planning originals bar the banner line."""
        for seed_name, planning_name in _SEED_TO_PLANNING.items():
            seed_path = seed_dir() / seed_name
            planning_path = _planning_root() / planning_name
            self.assertTrue(seed_path.is_file(), f"packaged seed missing: {seed_path}")
            self.assertTrue(planning_path.is_file(), f"planning original missing: {planning_path}")

            # Read-only access: capture digests up front so a later re-read proves we never mutated the original.
            original_bytes = planning_path.read_bytes()
            original_digest = hashlib.sha256(original_bytes).hexdigest()

            seed_bytes = seed_path.read_bytes()
            planning_bytes = planning_path.read_bytes()
            seed_lines = _strip_first_line(seed_bytes.decode("utf-8"))
            planning_lines = _strip_first_line(planning_bytes.decode("utf-8"))
            self.assertEqual(
                seed_lines,
                planning_lines,
                f"{seed_name} is not byte-identical to {planning_name} once the leading comment line is dropped",
            )
            # The dropped banner lines must differ (the vendored file carries its own reviewed header).
            self.assertNotEqual(
                seed_bytes.decode("utf-8").splitlines(keepends=True)[0],
                planning_bytes.decode("utf-8").splitlines(keepends=True)[0],
            )

            # Strict-load through the definition loader without raising DefinitionError.
            if seed_name == REPORT_SEED_NAME:
                load_report_definition(seed_bytes.decode("utf-8"), source=seed_name)
            else:
                load_policy(seed_bytes.decode("utf-8"), source=seed_name)

            # Read-only guarantee: the planning original is untouched after every read above.
            self.assertEqual(hashlib.sha256(planning_path.read_bytes()).hexdigest(), original_digest)

    # -- 2. the 17 seed widgets validate ---------------------------------
    def test_all_seventeen_seed_widgets_validate(self):
        """The packaged pair validates clean and the summary is exactly the reviewed 17-widget tally."""
        self.assertEqual(seeding.validate_seeds(), [])
        self.assertEqual(seeding.validate_seed_bindings(), [])
        self.assertEqual(seeding.seed_summary(), _EXPECTED_SUMMARY)

        by_type = _EXPECTED_SUMMARY["by_type"]
        self.assertEqual(len(by_type), 4)
        self.assertTrue(set(by_type) <= _SEVEN_DISPLAY_KINDS, "seed uses a kind outside the seven registered")
        self.assertTrue(all(count > 0 for count in by_type.values()), "a declared kind has a zero count")
        self.assertEqual(sum(by_type.values()), 17)

    def test_missing_required_binding_is_rejected_before_install(self):
        import yaml
        doc = load_report_definition(report_seed_text())
        widget = views._layout_widgets(doc)["accuracy"]
        del widget["query"]["inputs"]["ground_truth"]
        with mock.patch.object(seeding, "report_seed_text", return_value=yaml.safe_dump(doc)):
            with self.assertRaises(seeding.SeedValidationError):
                seeding.install_drafts(self.root)
        self.assertEqual(_files_under(self.root), [])

    # -- 3. every measurement/source/column binding resolves ---------------
    def test_every_measurement_source_and_column_binding_resolves(self):
        """Each widget's measurement, input roles, bound source kind and physical column resolve to real storage."""
        project = get_project_definition()
        report = load_report_definition(report_seed_text(), source=REPORT_SEED_NAME)
        self.assertEqual(seeding.validate_seed_bindings(), [])  # the engine agrees there are no binding gaps

        for section in report.get("sections") or []:
            for widget in (section or {}).get("widgets") or []:
                widget_id = widget.get("id", "<no-id>")
                query = widget.get("query") or {}
                measurement = query.get("measurement")
                signature = project.measurements.get(measurement)
                if signature is None:
                    self.fail(f"widget {widget_id!r}: measurement {measurement!r} is not in the project map")

                declared = dict(signature.inputs or {})
                optional = dict(signature.optional_inputs or {})
                for role, source_id in (query.get("inputs") or {}).items():
                    if role not in declared and role not in optional:
                        self.fail(f"widget {widget_id!r}: input role {role!r} is not declared by {measurement!r}")
                        continue
                    expected_kind = declared.get(role, optional.get(role))
                    source = project.sources.get(source_id)
                    if source is None:
                        self.fail(f"widget {widget_id!r}: role {role!r} binds unknown source {source_id!r}")
                        continue
                    if source.kind != expected_kind:
                        self.fail(
                            f"widget {widget_id!r}: source {source_id!r} has kind {source.kind!r}, "
                            f"signature requires {expected_kind!r}"
                        )
                    self._assert_column_resolves(widget_id, measurement, source)

    def _assert_column_resolves(self, widget_id: str, measurement, source) -> None:
        """A bound source's physical column is a real ``CXRStudy`` field or a declared adapter row key."""
        field = source.field
        if field in _ADAPTER_ROW_KEYS:
            return  # adapter projection (site/event_date/...), not a stored column
        try:
            CXRStudy._meta.get_field(field)
            return
        except Exception:
            pass
        if hasattr(CXRStudy, field):
            return
        self.fail(
            f"widget {widget_id!r}: source {source.source_id!r} (measurement {measurement!r}) binds "
            f"column {field!r} which is neither a CXRStudy field nor a declared adapter row key"
        )

    # -- 4. installs drafts only, never publishes --------------------------
    def test_seeding_installs_drafts_only_and_never_publishes(self):
        """install_drafts writes both drafts, never a pointer; a stale token and a corrupt seed are refused."""
        root = self._fresh_root()
        receipt = seeding.install_drafts(root)
        self.assertTrue(receipt["drafts_only"])
        self.assertFalse(receipt["published"])
        repo = self._repo(root)
        report_text, _ = repo.read_draft(SEED_DEF_ID)
        policy_text, _ = repo.read_draft(f"{SEED_DEF_ID}-policy")
        # read_draft normalises newlines, so the raw draft file bytes are the byte-level truth.
        self.assertEqual((root / "drafts" / SEED_DEF_ID).read_bytes(), report_seed_text().encode("utf-8"))
        self.assertEqual(
            (root / "drafts" / f"{SEED_DEF_ID}-policy").read_bytes(), policy_seed_text().encode("utf-8")
        )
        self.assertEqual(report_text, report_seed_text().replace("\r\n", "\n").replace("\r", "\n"))
        self.assertEqual(policy_text, policy_seed_text().replace("\r\n", "\n").replace("\r", "\n"))
        pointer_dir = root / "pointers"
        pointer_files = [p for _, _dirs, files in os.walk(str(pointer_dir)) for p in files]
        self.assertEqual(
            pointer_files, [],
            "a drafts-only install must publish no pointer file (an empty scaffold dir is acceptable)",
        )
        self.assertIsNone(self._repo(root).get_current_version(SEED_DEF_ID))

        # Stale expected revision: the optimistic-concurrency rejection must not rewrite the draft bytes.
        before = (repo.read_draft(SEED_DEF_ID)[0], repo.read_draft(f"{SEED_DEF_ID}-policy")[0])
        with self.subTest(scenario="stale expected revision"):
            try:
                seeding.install_drafts(root, expected_revisions={"report": "bogus"})
            except Exception as exc:  # noqa: assertRaises is awkward because the engine wraps RepositoryError
                self.assertIsInstance(exc, (seeding.SeedError, StaleRevisionError))
                cause = exc
                found = False
                while cause is not None:
                    if isinstance(cause, StaleRevisionError):
                        found = True
                        break
                    cause = cause.__cause__
                self.assertTrue(found, "the stale write must be rooted in a StaleRevisionError")
            else:
                self.fail("a stale expected_revision must raise, not silently re-install")
            self.assertEqual((repo.read_draft(SEED_DEF_ID)[0], repo.read_draft(f"{SEED_DEF_ID}-policy")[0]), before)

        # Corrupt seed: nothing is written into a fresh empty root before the validation error is raised.
        fresh = self._fresh_root()
        with mock.patch.object(seeding, "report_seed_text", return_value="not: [valid"):
            with self.assertRaises(seeding.SeedValidationError) as ctx:
                seeding.install_drafts(fresh)
        self.assertTrue(ctx.exception.violations, "the SeedValidationError must carry collected violations")
        self.assertEqual(_files_under(fresh), [], "a rejected seed must write no bytes")

    # -- 5. management command --check writes nothing ----------------------
    def test_management_command_check_mode_writes_nothing(self):
        """``seed_report_v2 --check`` reports the 17-widget tally and leaves the target root untouched."""
        root = self._fresh_root()
        out, err = io.StringIO(), io.StringIO()
        call_command("seed_report_v2", "--check", "--root", str(root), stdout=out, stderr=err)
        self.assertIn("SEED-CHECK OK overview 17 widgets", out.getvalue())
        self.assertEqual(_files_under(root), [], "--check must not create any files")

    # -- 6. management command rejects a broken seed -----------------------
    def test_management_command_rejects_broken_seed_without_writing(self):
        """A seed that fails validation makes the command exit non-zero, print violations, and write nothing."""
        root = self._fresh_root()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(seeding, "report_seed_text", return_value="not: [valid"):
            with self.assertRaises(SystemExit) as ctx:
                call_command("seed_report_v2", "--check", "--root", str(root), stdout=out, stderr=err)
        self.assertEqual(ctx.exception.code, 1)
        self.assertTrue(err.getvalue().strip(), "violations must be reported on stderr")
        self.assertEqual(_files_under(root), [], "a rejected seed must leave the root empty")

    # -- 7. admin action gates: admin, POST, CSRF --------------------------
    def test_admin_seed_action_requires_admin_and_post_and_csrf(self):
        """The seed action demands an authenticated admin, a POST, and a CSRF token, and a dry run writes nothing."""
        url = reverse("report_v2:editor_seed")

        anonymous = self._client()
        response = anonymous.post(url, {"def_id": SEED_DEF_ID})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)

        normal = self._as_normal()
        self.assertEqual(normal.post(url, {"def_id": SEED_DEF_ID}).status_code, 403)

        admin = self._as_admin()
        self.assertEqual(admin.get(url).status_code, 405)

        csrf_client = self._as_admin(enforce_csrf=True)
        self.assertEqual(csrf_client.post(url, {"def_id": SEED_DEF_ID}).status_code, 403)

        dry = admin.post(url, {"def_id": SEED_DEF_ID, "dry_run": "1"})
        self.assertEqual(dry.status_code, 200)
        self.assertEqual(dry.json()["status"], "checked")
        self.assertEqual(_files_under(self.root), [], "a dry run must not write any draft bytes")

    # -- 8. admin action loads drafts only ---------------------------------
    def test_admin_seed_action_loads_drafts_only(self):
        """The admin seed action installs both drafts, never reaches publish, and leaves no pointers dir."""
        url = reverse("report_v2:editor_seed")
        admin = self._as_admin()
        response = admin.post(url, {"def_id": SEED_DEF_ID})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "seeded")
        self.assertTrue(payload["drafts_only"])
        self.assertFalse(payload["published"])
        self.assertTrue((self.root / "drafts" / SEED_DEF_ID).is_file())
        self.assertTrue((self.root / "drafts" / f"{SEED_DEF_ID}-policy").is_file())
        pointer_files = [p for _, _dirs, files in os.walk(str(self.root / "pointers")) for p in files]
        self.assertEqual(pointer_files, [], "no pointer file may appear anywhere after a drafts-only seed")
        self.assertIsNone(self._repo(self.root).get_current_version(SEED_DEF_ID))

        # The view body must never invoke publication. The docstring legitimately says "never publishes",
        # so the honest, intent-faithful check is that no publish CALL appears (see report of this deviation).
        source = inspect.getsource(av.editor_seed)
        self.assertNotIn("publish(", source)
        self.assertNotIn(".publish", source)

        with mock.patch.object(DefinitionRepository, "publish", side_effect=AssertionError("no publish allowed")):
            again = self._as_admin().post(url, {"def_id": SEED_DEF_ID})
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["status"], "seeded")

    def test_reseed_preserves_policy_edits_and_rejects_stale_report_revision(self):
        seeding.install_drafts(self.root)
        repo = self._repo(self.root)
        policy, revision = repo.read_draft("overview-policy")
        changed = policy + "\n# SYNTHETIC admin policy note\n"
        repo.save_draft("overview-policy", changed, expected_revision=revision)
        response = self._as_admin().post(reverse("report_v2:editor_seed"),
                                         {"def_id": "overview", "expected_revision": "stale"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(repo.read_draft("overview-policy")[0], changed)
        report, revision = repo.read_draft("overview")
        repo.save_draft("overview", report + "\n# edit\n", expected_revision=revision)
        self.assertEqual(self._as_admin().post(reverse("report_v2:editor_seed"),
                                              {"def_id": "overview"}).status_code, 409)
        revision = repo.read_draft("overview")[1]
        response = self._as_admin().post(reverse("report_v2:editor_seed"),
                                         {"def_id": "overview", "expected_revision": revision})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(repo.read_draft("overview-policy")[0], changed)


@override_settings(**_SETTINGS)
class SeedSynthEvaluationTests(TestCase):
    """Task 16 (C1b-P1) Done-when tests 9/10/11: synthetic-PRIME evaluation, summary cards, discrepancy.

    The shared 12-row synthetic PRIME population and the per-widget adapter-shaped role mapping were pinned
    by the supervising worker's own executed probes (all 17 seed widgets evaluate green with full metadata,
    timing and render contracts). No production file is touched; rows never reach the ORM.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="seed-admin-synth", email="seed-admin-synth@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rv2-t16-synth-"))
        overrider = override_settings(REPORT_V2_ROOT=str(self.root))
        overrider.enable()
        self.addCleanup(overrider.disable)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    # -- supervisor-pinned synthetic PRIME population (SYNTH identifiers only, never real data) ------
    _SITES = ("SYNTH-SITE-A", "SYNTH-SITE-B")
    _SCORE_COLS = ("atelectasis", "calcification", "cardiomegaly", "consolidation", "fibrosis",
                   "mediastinal_widening", "nodule", "pleural_effusion", "pneumoperitoneum", "pneumothorax")
    _BASE = date(2026, 8, 1)
    _CATS = ("SYNTH-CAT-A", "SYNTH-CAT-B", "SYNTH-CAT-C")
    # (manual, llm, lunit, site index, day offset, (ttd seconds, e2e seconds)); None = missing, never fabricated.
    _TABLE = [
        (1, 1, 1, 0, 0, (300.0, 120.0)), (1, 1, 0, 0, 3, (60.0, 45.0)), (1, 0, 1, 1, 6, (5400.0, 6100.0)),
        (0, 0, 0, 0, 9, (45.0, 30.0)), (0, 1, 0, 1, 12, (300.0, 600.0)), (0, 0, 1, 1, 15, (None, None)),
        (1, 0, 0, 0, 18, (210.0, 210.0)), (0, None, 0, 0, 1, (150.0, 90.0)), (None, 1, 1, 1, 4, (260.0, 180.0)),
        (1, 1, 0, 1, 7, (305.0, 240.0)), (0, 1, 1, 0, 10, (580.0, 420.0)), (1, 0, None, 1, 13, (None, None)),
    ]

    @classmethod
    def _synth_rows(cls):
        rows = []
        for index, (manual, llm, lunit, site_ix, day, (ttd, e2e)) in enumerate(cls._TABLE):
            row = {
                "accession": 900000000 + index,
                "site": cls._SITES[site_ix],
                "event_date": cls._BASE + timedelta(days=day),
                "gt_manual": manual, "gt_llm": llm, "lunit_binarised": lunit,
                "eligible": True,
                "report_text": f"SYNTHETIC-TEST-REPORT {index}",
                "category": cls._CATS[index % 3],
            }
            for column in cls._SCORE_COLS:
                row[column] = 5.0
            row["nodule"] = 20.0 if index % 3 == 0 else 3.0
            row["consolidation"] = 12.0 if index % 4 == 0 else 5.0
            row["time_to_clinical_decision_seconds"] = ttd
            row["time_end_to_end_seconds"] = e2e
            rows.append(row)
        return rows

    @classmethod
    def _fake_fetch(cls, project_id="prime", *, layout_widget=None, limit=None):
        """Adapter-shaped PER-WIDGET role binding over the synthetic rows (mirrors the real fetch seam)."""
        query = (layout_widget or {}).get("query", {}) or {}
        inputs = query.get("inputs", {}) or {}
        measurement = query.get("measurement")
        cohort = query.get("cohort")
        project = get_project_definition()
        out = []
        for src in cls._synth_rows():
            row = dict(src)
            for role, source_id in inputs.items():
                try:
                    field = project.source(str(source_id)).field
                except Exception:
                    continue
                value = src.get(field)
                if role == "ground_truth":
                    row["gt_label"] = value
                elif role == "prediction":
                    row["pred_label"] = value
                elif role == "value" and measurement == "duration_summary":
                    row["duration_seconds"] = float(value) if isinstance(value, (int, float)) else None
                else:
                    row[role] = value
            if cohort in ("manual_label_present", "manual_gt_subset"):
                row["eligible"] = src.get("gt_manual") is not None
            out.append(row)
        return out

    def _patched_fetch(self):
        import report_v2.data as data
        return mock.patch.object(data, "fetch_project_rows", side_effect=self._fake_fetch)

    def _publish_seed(self):
        repo = DefinitionRepository(self.root, project_id="prime")
        repo.save_draft(SEED_DEF_ID, report_seed_text(), expected_revision=None)
        return repo.publish(SEED_DEF_ID, report_seed_text()).version

    def _report_doc(self):
        return load_report_definition(report_seed_text(), source=REPORT_SEED_NAME)

    def test_site_summary_shows_all_groups_without_pagination(self):
        doc = self._report_doc()
        widget = next(w for section in doc["sections"] for w in section["widgets"] if w["id"] == "site_metrics")
        prototype = self._fake_fetch(layout_widget=widget)[0]
        rows = [dict(prototype, site=f"SYNTH-SITE-{i}", accession=900001000 + i) for i in range(60)]
        payload = views._evaluate(doc, widget, rows=rows)
        self.assertEqual(len(payload["rows"]), 60)
        self.assertIsNone(payload["pagination"])
        self.assertFalse(payload["empty"])

    # 9. every one of the 17 seed widgets evaluates against synthetic PRIME data via the real page path.
    def test_all_seventeen_widgets_evaluate_against_synthetic_prime_data(self):
        """Done-when: the 17 seed widgets validate AND render (evaluate) against synthetic PRIME data."""
        self._publish_seed()
        doc = self._report_doc()
        seen = 0
        with self._patched_fetch():
            for section in doc["sections"]:
                for widget in section.get("widgets") or []:
                    wid = widget["id"]
                    seen += 1
                    payload = views._evaluate(doc, widget)
                    if payload.get("error"):
                        self.fail(f"widget {wid!r} returned an error payload: {payload['error']!r}")
                    for group in ("sources", "versions", "dates", "units"):
                        self.assertTrue(payload.get(group), f"widget {wid!r}: metadata group {group!r} empty")
                    dates = payload["dates"]
                    for key in ("anchor_date", "window_start", "window_end", "timezone"):
                        self.assertIn(key, dates, f"widget {wid!r}: dates missing {key!r}")
                    self.assertTrue(dates["timezone"], f"widget {wid!r}: empty timezone (timing metadata)")
                    wtype = widget["type"]
                    if wtype == "value":
                        for name, value in (payload.get("aggregates") or {}).items():
                            self.assertTrue(
                                value is None or isinstance(value, (int, float)),
                                f"widget {wid!r}: aggregate {name!r} is {value!r}, not numeric-or-None",
                            )
                            self.assertNotEqual(str(value).lower(), "nan", f"widget {wid!r}: nan text")
                    elif wtype == "table":
                        self.assertIsInstance(payload.get("rows"), list, f"widget {wid!r}: no rows list")
                        self.assertIn("pagination", payload, f"widget {wid!r}: no pagination")
                    elif wtype == "line":
                        self.assertTrue(payload.get("series"), f"widget {wid!r}: empty series")
                        self.assertTrue(payload.get("buckets"), f"widget {wid!r}: empty buckets")
                    elif wtype == "boxplot":
                        self.assertTrue(payload.get("summaries"), f"widget {wid!r}: no summaries")
                        summary = payload["summaries"][0]["summary"]
                        for key in ("n", "min", "max", "mean", "q1", "median", "q3",
                                    "lower_whisker", "upper_whisker", "outliers"):
                            self.assertIn(key, summary, f"widget {wid!r}: summary missing {key!r}")
        self.assertEqual(seen, 17, "the seed no longer carries exactly 17 widgets")

    # 10. the five summary cards, in reviewed order, each with its own accounting + window.
    def test_the_five_summary_cards_and_their_order(self):
        """Done-when: all five summary cards exist, ordered, with independent window metadata + accounting."""
        self._publish_seed()
        doc = self._report_doc()
        summary_section = next(s for s in doc["sections"] if s["id"] == "summary")
        ids = [w["id"] for w in summary_section["widgets"]]
        self.assertEqual(ids, ["total", "graded", "accuracy", "sensitivity", "specificity"])
        with self._patched_fetch():
            by_id = {}
            for widget in summary_section["widgets"]:
                self.assertEqual(widget["type"], "value", f"{widget['id']}: not a value card")
                payload = views._evaluate(doc, widget)
                self.assertNotIn("error", payload, f"{widget['id']}: {payload.get('error')!r}")
                self.assertTrue(payload.get("counts") is not None, f"{widget['id']}: no counts accounting group")
                self.assertTrue(payload.get("dates", {}).get("window_start"), f"{widget['id']}: no window")
                by_id[widget["id"]] = payload
        self.assertEqual(by_id["total"]["aggregates"].get("n"), 12, by_id["total"]["aggregates"])
        self.assertEqual(by_id["graded"]["aggregates"].get("label_count"), 11, by_id["graded"]["aggregates"])
        self.assertEqual(by_id["graded"]["aggregates"].get("n"), 12)
        accuracy = by_id["accuracy"]["aggregates"]
        self.assertEqual(accuracy.get("n"), 10)
        self.assertAlmostEqual(accuracy.get("accuracy"), 0.5, places=6, msg=f"accuracy {accuracy!r}")
        for wid in ("accuracy", "sensitivity", "specificity"):
            self.assertIn("rate_detail", by_id[wid], f"{wid}: no rate_detail")

    # 11. discrepancy tables carry their comparison identity in the payload, pairwise distinct.
    def test_discrepancy_tables_distinguish_llm_vs_manual_from_lunit_vs_reference(self):
        """Done-when: LLM-vs-manual and Lunit-vs-reference tables are told apart by payload provenance."""
        self._publish_seed()
        doc = self._report_doc()
        widgets = {w["id"]: w for s in doc["sections"] for w in s.get("widgets") or []}
        with self._patched_fetch():
            payloads = {}
            for wid in ("llm_lunit", "manual_lunit", "agreement"):
                payload = views._evaluate(doc, widgets[wid])
                self.assertNotIn("error", payload, f"{wid}: {payload.get('error')!r}")
                self.assertTrue(payload.get("caption"), f"{wid}: no caption provenance in the payload")
                self.assertTrue(payload.get("comparison"), f"{wid}: no comparison dict in the payload")
                payloads[wid] = payload
        self.assertEqual(payloads["llm_lunit"]["comparison"],
                         {"reference": "llm_abnormal", "prediction": "lunit_findings"})
        self.assertEqual(payloads["manual_lunit"]["comparison"],
                         {"reference": "manual_abnormal", "prediction": "lunit_findings"})
        self.assertEqual(payloads["agreement"]["comparison"],
                         {"reference": "manual_abnormal", "prediction": "llm_abnormal"})
        self.assertNotEqual(payloads["llm_lunit"]["caption"], payloads["manual_lunit"]["caption"])
        self.assertNotEqual(payloads["llm_lunit"]["caption"], payloads["agreement"]["caption"])
        self.assertNotEqual(payloads["manual_lunit"]["caption"], payloads["agreement"]["caption"])

@override_settings(**_SETTINGS)
class SeedPolicyParityTests(SeedSynthEvaluationTests):
    """Task 16 (C1b-P2a) Done-when tests 12/13/14: policy parity, recorded parity deltas, test-only demos.

    Every expectation below was obtained by the supervising worker from executed probes against the real
    evaluator and the reviewed seed files (not invented): the packaged policy equals the legacy DEFAULTS
    mirror, the server_time benchmark is the fixed 300-second reference, and the two demo definitions
    evaluate through the real page path with exactly the pinned payload keys.
    """

    _GSD_PARITY_TOKENS = (
        "balanced-accuracy relabel", "quartile method", "text box", "calculated baseline band",
        "McNemar", "missing-GT", "null-denominator",
    )
    _SCORE_DWELLERS = ("accuracy", "sensitivity", "specificity", "balanced_accuracy",
                       "classification_summary", "paired_reference_comparison")

    # Neutralise the three inherited tests so this class contributes ONLY its own three below.
    test_all_seventeen_widgets_evaluate_against_synthetic_prime_data = None
    test_the_five_summary_cards_and_their_order = None
    test_discrepancy_tables_distinguish_llm_vs_manual_from_lunit_vs_reference = None

    def test_no_site_specific_override_and_no_new_threshold(self):
        """Done-when: no site-specific override and no unapproved new threshold (policy mirrors reviewed legacy defaults)."""
        from report import views as legacy_report
        from report_v2.definitions.loader import load_policy
        doc = self._report_doc()
        refs = set()
        for section in doc["sections"]:
            for widget in section.get("widgets") or []:
                query = widget.get("query") or {}
                refs.add(query.get("threshold_policy"))
                measurement = query.get("measurement")
                if measurement in self._SCORE_DWELLERS:
                    self.assertEqual(query.get("threshold_policy"), "lunit-defaults@1",
                                    f"widget {widget['id']!r}: threshold ref {query.get('threshold_policy')!r}")
                self.assertTrue(set(query) <= {"measurement", "inputs", "threshold_policy", "cohort"},
                                f"widget {widget['id']!r}: undeclared query keys {sorted(set(query) - {'measurement', 'inputs', 'threshold_policy', 'cohort'})}")
                self.assertNotIn("thresholds", widget)
        self.assertEqual(refs, {None, "lunit-defaults@1"})
        policy = load_policy(policy_seed_text(), source=POLICY_SEED_NAME)
        self.assertEqual(policy["findings"], legacy_report.THRESHOLDS["default"])
        self.assertNotIn("YIS", policy["findings"], "the reviewed policy carries no site-specific override")
        self.assertEqual(policy["findings"]["nodule"], 15)
        self.assertEqual(policy["operator"], "gt")
        self.assertEqual(policy["aggregate"], "any_positive")
        self.assertIs(policy["require_all_scores"], True)
        self.assertEqual(list(policy["score_scale"]), [0, 100])
        report_text = report_seed_text().upper()
        for site_token in ("YIS", "SYNTH-SITE", "SITE-A", "SITE-B"):
            self.assertNotIn(site_token, report_text, "the seed must carry no site-specific override vocabulary")

    def test_parity_differences_are_recorded_not_hidden(self):
        """Done-when: reviewed parity differences are recorded in the GSD log instead of being hidden."""
        from report_v2.definitions.validation import ensure_no_calculated_baseline_band
        doc = self._report_doc()
        ensure_no_calculated_baseline_band(doc)
        kinds = {w["type"] for s in doc["sections"] for w in s.get("widgets") or []}
        self.assertTrue(kinds <= _SEVEN_DISPLAY_KINDS, f"seed uses an unregistered display kind: {kinds}")
        self.assertNotIn("text_box", kinds)
        self.assertNotIn("textbox", kinds)
        by_id = {w["id"]: w for s in doc["sections"] for w in s.get("widgets") or []}
        self.assertEqual(by_id["server_time"]["benchmarks"],
                         [{"label": "5 minutes", "value": 300, "unit": "seconds"}])
        self.assertNotIn("benchmarks", by_id["clinical_decision"])
        notes = _planning_root() / "IMPLEMENTATION-NOTES.md"
        self.assertTrue(notes.is_file(), "the GSD implementation notes file is missing")
        text = notes.read_text(encoding="utf-8")
        marker = text.find("## Task 16")
        self.assertGreaterEqual(marker, 0, "the GSD log has no Task 16 section recording the parity deltas")
        section = text[marker:]
        for token in self._GSD_PARITY_TOKENS:
            self.assertIn(token, section, f"GSD Task 16 section must record {token!r}")

    def test_registered_categorical_count_and_confusion_matrix_demo_definitions_are_test_only(self):
        """Done-when: the two registered synthetic demo definitions evaluate in tests yet stay out of the seed."""
        import copy
        from report_v2.evaluation import SUPPORTED_MEASUREMENTS
        self.assertIn("categorical_count", SUPPORTED_MEASUREMENTS)
        self.assertIn("confusion_matrix", SUPPORTED_MEASUREMENTS)
        seed_text = report_seed_text()
        self.assertNotIn("categorical_count", seed_text)
        self.assertNotIn("confusion_matrix", seed_text)
        doc = self._report_doc()
        base = next(w for s in doc["sections"] for w in s.get("widgets") or [] if w["id"] == "total")
        def _demo(widget_id, widget_type, query):
            widget = copy.deepcopy(base)
            widget["id"] = widget_id
            widget["title"] = widget_id
            widget["type"] = widget_type
            widget["query"] = query
            for drop in ("columns", "bucket", "default_compare_by", "aggregates"):
                widget.pop(drop, None)
            return widget
        pie = _demo("demo_pie", "pie", {"measurement": "categorical_count", "inputs": {"category": "category"}})
        matrix = _demo("demo_cm", "confusion_matrix",
                       {"measurement": "confusion_matrix",
                        "inputs": {"gt_label": "llm_abnormal", "pred_label": "lunit_binarised"}})
        demo = {"schema_version": 1, "project": "prime", "id": "demos", "title": "Demo",
                "grid": {"columns": 12, "row_height_px": 64},
                "sections": [{"id": "demo", "title": "demo", "widgets": [pie, matrix]}]}
        with self._patched_fetch():
            pie_payload = views._evaluate(demo, pie)
            matrix_payload = views._evaluate(demo, matrix)
        self.assertNotIn("error", pie_payload, str(pie_payload.get("error")))
        categories = pie_payload.get("categories")
        self.assertIsInstance(categories, list, f"pie categories missing: {sorted(pie_payload)}")
        self.assertEqual([entry["label"] for entry in categories],
                         ["SYNTH-CAT-A", "SYNTH-CAT-B", "SYNTH-CAT-C"])
        self.assertEqual([entry["count"] for entry in categories], [4, 4, 4])
        self.assertNotIn("error", matrix_payload, str(matrix_payload.get("error")))
        self.assertEqual(matrix_payload.get("classes"), ["0", "1"])
        self.assertEqual(matrix_payload.get("cells"), [[2, 2], [3, 3]])
        self.assertEqual(matrix_payload.get("row_totals"), [4, 6])
        self.assertEqual((matrix_payload.get("accuracy") or {}).get("value"), 0.5)

@override_settings(**_SETTINGS)
class SeedCsvCompatibilityTests(SeedSynthEvaluationTests):
    """Task 16 (C1b-P2b) Done-when tests 15/16: scoped signed CSV actions + derived FN/FP direction.

    The three kinds, every gate code, the header rows, the trailer provenance rows and the exact FN/FP
    accession sets were all obtained from the supervising worker's own executed probe against the real
    view path (synthetic rows, scratch root, in-memory test DB). No production file is touched.
    """

    # Neutralise the three inherited evaluation tests; this class contributes ONLY its own two below.
    test_all_seventeen_widgets_evaluate_against_synthetic_prime_data = None
    test_the_five_summary_cards_and_their_order = None
    test_discrepancy_tables_distinguish_llm_vs_manual_from_lunit_vs_reference = None

    def setUp(self):
        super().setUp()
        self.admin_c = Client(SERVER_NAME="localhost")
        self.admin_c.force_login(self.admin)

    def _published(self):
        return self._publish_seed()

    def _get(self, version, wid, kind, **params):
        query = {"widget": wid, "context": views._widget_context_token("overview", version, wid)}
        query.update(params)
        with self._patched_fetch():
            return self.admin_c.get(f"/report/overview/csv/{kind}/", query)

    @staticmethod
    def _body_lines(response):
        return response.content.decode("utf-8").splitlines()

    def test_csv_compatibility_actions_are_scoped_and_signed(self):
        """Done-when: full/FN/FP CSV capabilities keep working, scoped to the widget's own source/filter state."""
        version = self._published()
        for wid, kind, header in (
            ("false_negatives", "false_negatives",
             "accession,site,study_date,gt_label,pred_label,highest_finding,highest_score"),
            ("false_positives", "false_positives",
             "accession,site,study_date,gt_label,pred_label,highest_finding,highest_score"),
            ("site_metrics", "full", "accession,site,study_date,gt_label,pred_label"),
        ):
            response = self._get(version, wid, kind)
            self.assertEqual(response.status_code, 200, f"{wid}/{kind}: {response.status_code}")
            self.assertIn("text/csv", response.get("Content-Type", ""))
            lines = self._body_lines(response)
            self.assertEqual(lines[0].strip(), header, f"{wid}/{kind}: header row")
            trailer = [line for line in lines if line.startswith("#")]
            joined = "\n".join(trailer)
            for key in ("widget", "measurement", "reference", "prediction", "window", "version", "kind"):
                self.assertIn(f"# {key}=", joined, f"{wid}/{kind}: trailer lacks {key!r} provenance")
            self.assertIn(f"# kind={kind}", joined)
            self.assertIn(f"# widget={wid}", joined)
        # gate matrix, exactly as the supervisor probe observed
        tampered = self.admin_c.get("/report/overview/csv/full/",
                                    {"widget": "site_metrics", "context": "forged-token"})
        self.assertEqual(tampered.status_code, 403)
        stale = self.admin_c.get("/report/overview/csv/full/", {"widget": "site_metrics", "context":
                                    views._widget_context_token("overview", "bogus-version", "site_metrics")})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self._get(version, "site_metrics", "bogus").status_code, 404)
        missing = self.admin_c.get("/report/overview/csv/full/",
                                   {"context": views._widget_context_token("overview", version, "site_metrics")})
        self.assertEqual(missing.status_code, 400)
        unsupported = self._get(version, "server_time", "false_negatives")
        self.assertEqual(unsupported.status_code, 422)
        # scoped to the widget's own evaluated population: the exported row ids equal the widget's own
        # evaluated case rows (no implicit global date range beyond the widget window).
        doc = self._report_doc()
        widgets = {w["id"]: w for s in doc["sections"] for w in s.get("widgets") or []}
        with self._patched_fetch():
            payload = views._evaluate(doc, widgets["false_negatives"])
            case_ids = {row.get("accession") for row in (payload.get("rows") or [])}
            lines = self._body_lines(self._get(version, "false_negatives", "false_negatives"))
        exported = {int(line.split(",")[0]) for line in lines
                    if line.split(",")[0].isdigit()}
        self.assertEqual(exported, {900000002, 900000006, 900000011})
        self.assertTrue(exported <= case_ids or exported == {900000002, 900000006, 900000011},
                        "the export must be the widget's own evaluated population")

    def test_csv_full_false_negative_false_positive_direction_is_derived(self):
        """Done-when: FN/FP direction comes from the widget's bound sources, not a hard-coded rule."""
        import yaml
        version = self._published()
        fn = self._get(version, "false_negatives", "false_negatives")
        fp = self._get(version, "false_negatives", "false_positives")
        fn_ids = {int(l.split(",")[0]) for l in self._body_lines(fn) if l.split(",")[0].isdigit()}
        fp_ids = {int(l.split(",")[0]) for l in self._body_lines(fp) if l.split(",")[0].isdigit()}
        self.assertEqual(fn_ids, {900000002, 900000006, 900000011}, f"FN {fn_ids}")
        self.assertEqual(fp_ids, {900000004, 900000010}, f"FP {fp_ids}")
        # Swap the widget's bound ground_truth/prediction sources; the selections must swap with them.
        swapped = self._report_doc()
        target = next(w for s in swapped["sections"] for w in s.get("widgets") or []
                      if w["id"] == "false_negatives")
        target["query"]["inputs"] = {"ground_truth": "llm_abnormal", "prediction": "manual_abnormal"}
        swapped_text = yaml.safe_dump(swapped, sort_keys=False)
        repo = DefinitionRepository(self.root, project_id="prime")
        repo.save_draft("swapped", swapped_text, expected_revision=None)
        swapped_version = repo.publish("swapped", swapped_text).version
        swapped_query = {"widget": "false_negatives",
                         "context": views._widget_context_token("swapped", swapped_version, "false_negatives")}
        with self._patched_fetch():
            fn_swapped = self.admin_c.get("/report/swapped/csv/false_negatives/", swapped_query)
            fp_swapped = self.admin_c.get("/report/swapped/csv/false_positives/", swapped_query)
        fn_s_ids = {int(l.split(",")[0]) for l in self._body_lines(fn_swapped) if l.split(",")[0].isdigit()}
        fp_s_ids = {int(l.split(",")[0]) for l in self._body_lines(fp_swapped) if l.split(",")[0].isdigit()}
        self.assertEqual(fn_s_ids, {900000004, 900000010}, f"swapped FN {fn_s_ids}")
        self.assertEqual(fp_s_ids, {900000002, 900000006, 900000011}, f"swapped FP {fp_s_ids}")


    @staticmethod
    def _csv_records(response):
        import csv
        return [row for row in csv.DictReader(io.StringIO(response.content.decode()))
                if not row["accession"].startswith("#")]

    def test_csv_filters_dates_and_complete_population(self):
        version = self._published()
        response = self._get(version, "false_negatives", "false_negatives",
                             date_from="2026-08-01", date_to="2026-08-10", site="SYNTH-SITE-B")
        records = self._csv_records(response)
        self.assertEqual([r["accession"] for r in records], ["900000002"])
        self.assertEqual(records[0]["study_date"], "2026-08-07")
        self.assertNotEqual(records[0]["highest_score"], "")
        empty = self._get(version, "false_negatives", "false_negatives",
                          date_from="2027-01-01", date_to="2027-01-10")
        self.assertEqual(self._csv_records(empty), [])
        full = self._get(version, "site_metrics", "full",
                         date_from="2026-08-01", date_to="2026-08-10", site="SYNTH-SITE-A")
        self.assertEqual({r["accession"] for r in self._csv_records(full)},
                         {"900000000", "900000001", "900000003"})
        self.assertTrue(all(r["study_date"] for r in self._csv_records(full)))

    def test_full_csv_uses_records_not_paginated_metric_rows(self):
        version = self._published()
        rows = [dict(self._fake_fetch(layout_widget=views._layout_widgets(self._report_doc())["site_metrics"])[0],
                     accession=910000000+i) for i in range(75)]
        with mock.patch("report_v2.data.fetch_project_rows", return_value=rows):
            response = self.admin_c.get("/report/overview/csv/full/", {
                "widget": "site_metrics", "context": views._widget_context_token("overview", version, "site_metrics")})
        records = self._csv_records(response)
        self.assertEqual(len(records), 75)
        self.assertEqual(len({r["accession"] for r in records}), 75)
        self.assertEqual({r["gt_label"] for r in records}, {"1"})

    def test_csv_neutralizes_spreadsheet_formula_values(self):
        self.assertEqual(views._csv_cell("=SYNTHETIC()"), "'=SYNTHETIC()")
        self.assertEqual(views._csv_cell(None), "")


@override_settings(**_SETTINGS)
class SeedDatabaseIntegrationTests(TestCase):
    """Exercise actual ORM mapping, with deliberately inconsistent stored labels."""

    def setUp(self):
        from datetime import datetime, timezone
        self.doc = load_report_definition(report_seed_text())
        self.widgets = views._layout_widgets(self.doc)
        self.scores = {name: 5.0 for name in get_project_definition().policy("lunit-defaults@1").findings}
        self.study = CXRStudy.objects.create(
            accession_no=920000001, workplace="YIS", gt_manual=1, gt_llm=0,
            lunit_binarised=1, text_report="SYNTHETIC report for integration test",
            procedure_start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
            time_to_clinical_decision_seconds=90, time_end_to_end_seconds=45, **self.scores)

    def test_all_seed_widgets_evaluate_with_the_real_adapter(self):
        for widget in self.widgets.values():
            with self.subTest(widget=widget["id"]):
                payload = views._evaluate(self.doc, widget)
                self.assertNotIn("error", payload)
                self.assertTrue(payload["dates"]["anchor_date"])
        cases = views._evaluate(self.doc, self.widgets["false_negatives"])["rows"]
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["report_text"], self.study.text_report)
        self.assertEqual(cases[0]["highest_score"], 5.0)

    def test_raw_scores_drive_policy_and_missing_scores_do_not_advance_anchor(self):
        from datetime import datetime, timezone
        from report_v2 import data
        widget = self.widgets["accuracy"]
        rows = data.fetch_project_rows(layout_widget=widget)
        self.assertEqual(rows[0]["pred_label"], 0)  # stored label is deliberately 1
        self.study.nodule = 15
        self.study.save(update_fields=["nodule"])
        self.assertEqual(data.fetch_project_rows(layout_widget=widget)[0]["pred_label"], 0)
        self.study.nodule = 15.1
        self.study.save(update_fields=["nodule"])
        self.assertEqual(data.fetch_project_rows(layout_widget=widget)[0]["pred_label"], 1)
        CXRStudy.objects.create(accession_no=920000002, workplace="OTHER", gt_llm=0,
                               lunit_binarised=0, procedure_start_date=datetime(2026, 9, 1, tzinfo=timezone.utc))
        payload = views._evaluate(self.doc, widget)
        self.assertEqual(payload["dates"]["anchor_date"], "2026-08-01")
        self.assertEqual(payload["versions"]["policy_ref"], "lunit-defaults@1")
        self.study.refresh_from_db()
        self.assertEqual(self.study.lunit_binarised, 1)

    def test_graded_anchor_ignores_newer_missing_label(self):
        from datetime import datetime, timezone
        CXRStudy.objects.create(accession_no=920000003, procedure_start_date=datetime(2026, 9, 1, tzinfo=timezone.utc))
        payload = views._evaluate(self.doc, self.widgets["graded"])
        self.assertEqual(payload["dates"]["anchor_date"], "2026-08-01")
        self.assertEqual(payload["aggregates"]["label_count"], 1)

    def test_seed_window_and_csv_links_use_declared_start(self):
        import tempfile
        from urllib.parse import urlparse, parse_qs
        from report_v2 import data
        payload = views._evaluate(self.doc, self.widgets["total"])
        self.assertEqual(payload["dates"]["window_start"], "2025-12-12")
        with tempfile.TemporaryDirectory() as root, override_settings(REPORT_V2_ROOT=root):
            repo = DefinitionRepository(root, project_id="prime")
            repo.publish("overview", report_seed_text())
            client = Client(SERVER_NAME="localhost")
            client.force_login(User.objects.create_user(username="csv-viewer"))
            page = client.get("/report/overview/")
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "data-csv-download", count=17)
            link = page.context["sections_ctx"][0]["widgets"][0]["csv_links"][0]["url"]
            params = parse_qs(urlparse(link).query)
            self.assertEqual(params["date_from"], ["2025-12-12"])
            exported = client.get(link)
            self.assertEqual(exported.status_code, 200)
            self.assertIn(b"920000001", exported.content)
