# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 19: end-to-end acceptance over the runbook's final checklist.

These tests are the recorded evidence for the EXECUTION-RUNBOOK acceptance checklist:
the full synthetic journey (editor publish -> viewer page -> per-widget filters ->
snapshot -> print -> email), two-report independence, legacy ``/report-old/``
preservation, an isolated ``collectstatic`` run with the production WhiteNoise storage,
source/dependency scans for the "nothing extra was added" items, and the initial YAML's
shape (17 widgets, seven display types, no monospaced text box).

Everything runs against synthetic rows through the Task-13 seam and the locmem mail
backend: no clinical record is read, no SMTP endpoint is contacted.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from report_v2 import snapshots
from report_v2.definitions.loader import load_report_definition
from report_v2.tests.test_pages import _SETTINGS, _Seam, _rows
from report_v2.tests.test_email import LAYOUT, _PNG_BYTES, _png_data_url

_SEVEN_DISPLAYS = {"value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"}


def _tokens(page_html: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'data-widget-id="([^"]+)"[^>]*data-context-token="([^"]+)"', page_html
        )
    }


@override_settings(**_SETTINGS)
class AcceptanceFlowTests(TestCase):
    """The runbook's editor -> publish -> viewer filters -> print/email journey, plus the checklist edges."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="t19-admin", email="t19-admin@example.invalid", password="pw-strong-1"
        )
        cls.normal = User.objects.create_user(
            username="t19-normal", email="t19-normal@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.defs_root = Path(tempfile.mkdtemp(prefix="t19-defs-"))
        defs_overrider = override_settings(REPORT_V2_ROOT=str(self.defs_root))
        defs_overrider.enable()
        self.addCleanup(defs_overrider.disable)
        self.snap_root = Path(tempfile.mkdtemp(prefix="t19-acc-"))
        snap_overrider = override_settings(REPORT_V2_SNAPSHOT_ROOT=str(self.snap_root))
        snap_overrider.enable()
        self.addCleanup(snap_overrider.disable)
        snapshots._reset_store_for_tests()
        self.addCleanup(snapshots._reset_store_for_tests)
        self.addCleanup(lambda: shutil.rmtree(self.defs_root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(self.snap_root, ignore_errors=True))
        self.seam = _Seam(good=_rows(3))
        patcher = mock.patch("report_v2.data.fetch_project_rows", self.seam)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers -----------------------------------------------------------
    def _publish(self, def_id: str, yaml_text: str) -> str:
        client = Client(SERVER_NAME="localhost")
        client.force_login(self.admin)
        response = client.post(
            "/report/layout/editor/publish/", {"def_id": def_id, "yaml_text": yaml_text}
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()["version"]

    def _login(self, user) -> Client:
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        return client

    # -- 1. the full synthetic journey --------------------------------------------------
    def test_editor_publish_viewer_filters_print_email_journey(self):
        slug = "t19report"
        version = self._publish(slug, LAYOUT)
        self.assertEqual(version, f"{slug}@r1")

        # Viewer opens the published page (fresh navigation = server defaults).
        client = self._login(self.normal)
        page = client.get(f"/report/{slug}/").content.decode("utf-8")
        tokens = _tokens(page)
        self.assertEqual(set(tokens), {"v1", "c1", "t1", "t2"})

        # Per-widget filters: v1 narrows to D-7 + site + comparison; sibling t2 stays default.
        v1_body = {
            "context": tokens["v1"],
            "date": {"relative": "D-7"},
            "filters": {"site": "SYNTH-SITE-A"},
            "comparison": "site",
        }
        v1 = client.post(
            f"/report/{slug}/widget/v1/data/", json.dumps(v1_body), content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(v1.status_code, 200, v1.content[:300])
        v1_payload = v1.json()
        self.assertEqual(v1_payload["status"], "ok")
        # D-7 is eight inclusive dates (D minus seven calendar days through D).
        self.assertEqual(v1_payload["dates"]["window_start"], "2026-08-25")
        t2 = client.post(
            f"/report/{slug}/widget/t2/data/", json.dumps({"context": tokens["t2"]}),
            content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(t2.status_code, 200)
        self.assertEqual(t2.json()["dates"]["window_start"], "2026-08-02")  # untouched D-30

        # Freeze the whole report under the CURRENT per-widget state and print it.
        body = {
            "settled": True,
            "widgets": [
                {"context": tokens["v1"], "date": {"relative": "D-7"},
                 "filters": {"site": "SYNTH-SITE-A"}, "comparison": "site"},
                {"context": tokens["c1"]},
                {"context": tokens["t1"]},
                {"context": tokens["t2"]},
            ],
        }
        frozen = client.post(
            f"/report/{slug}/snapshot/", json.dumps(body), content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(frozen.status_code, 201, frozen.content[:300])
        token = frozen.json()["token"]
        printed = client.get(f"/report/{slug}/print/{token}/")
        self.assertEqual(printed.status_code, 200)
        printed_html = printed.content.decode("utf-8")
        self.assertIn("window D-7", printed_html)       # v1 carries its own override
        self.assertIn("site=SYNTH-SITE-A", printed_html)
        self.assertIn("2026-08-02 .. 2026-09-01", printed_html)  # t2 kept its default window
        self.assertIn("compare by site", printed_html)
        self.assertIn(version, printed_html)

        # Email the SAME frozen state (locmem; one inline CID image for the pie).
        sent = client.post(
            f"/report/{slug}/email/",
            json.dumps({
                "snapshot": token,
                "recipients": ["audit@example.invalid"],
                "note": "Weekly review",
                "images": {"c1": _png_data_url()},
            }),
            content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(sent.status_code, 200, sent.content[:300])
        self.assertEqual(len(mail.outbox), 1)
        email_html = next(
            part.get_payload(decode=True).decode("utf-8")
            for part in mail.outbox[0].message().walk()
            if part.get_content_type() == "text/html"
        )
        self.assertIn('src="cid:c1@primer-llm"', email_html)
        self.assertIn("Weekly review", email_html)
        self.assertIn(version, email_html)
        duplicate = client.post(
            f"/report/{slug}/email/",
            json.dumps({
                "snapshot": token,
                "recipients": ["audit@example.invalid"],
                "note": "Weekly review",
                "images": {"c1": _png_data_url()},
            }),
            content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(duplicate.status_code, 409)  # duplicate-click prevention
        self.assertEqual(len(mail.outbox), 1)

    # -- 2. two independent reports in one project ---------------------------------------
    def test_two_reports_publish_and_view_independently(self):
        layout_a = LAYOUT.replace("id: t18report", "id: t19alpha").replace("title: Task 18 Report",
                                                                           "title: Alpha Report")
        layout_b = LAYOUT.replace("id: t18report", "id: t19beta").replace("title: Task 18 Report",
                                                                          "title: Beta Report")
        version_a = self._publish("t19alpha", layout_a)
        version_b = self._publish("t19beta", layout_b)

        # Both listed and viewable.
        client = self._login(self.normal)
        index = client.get("/report/").content.decode("utf-8")
        self.assertIn("/report/t19alpha/", index)
        self.assertIn("/report/t19beta/", index)
        page_a = client.get("/report/t19alpha/")
        page_b = client.get("/report/t19beta/")
        self.assertEqual(page_a.status_code, 200)
        self.assertEqual(page_b.status_code, 200)
        self.assertIn(b"Alpha Report", page_a.content)
        self.assertIn(b"Beta Report", page_b.content)

        # Republishing beta leaves alpha's pinned version untouched.
        self._publish("t19beta", layout_b.replace("title: Beta Report", "title: Beta Report Two"))
        again_b = client.get("/report/t19beta/")
        self.assertIn(b"Beta Report Two", again_b.content)
        again_a = client.get("/report/t19alpha/")
        self.assertIn(version_a.encode(), again_a.content)
        self.assertNotIn(b"Beta", again_a.content)
        self.assertEqual(version_b, "t19beta@r1")

    # -- 3. the legacy report keeps working untouched ------------------------------------
    def test_legacy_report_old_route_still_serves(self):
        anonymous = Client(SERVER_NAME="localhost")
        redirected = anonymous.get("/report-old/")
        self.assertEqual(redirected.status_code, 302)
        client = self._login(self.normal)
        legacy = client.get("/report-old/")
        self.assertEqual(legacy.status_code, 200)
        self.assertIn(b"Analysis Report", legacy.content)
        self.assertIn(b"Generate accuracy", legacy.content)

    # -- 4. static collection works in an isolated location ------------------------------
    def test_collectstatic_into_isolated_root_with_production_storage(self):
        static_root = Path(tempfile.mkdtemp(prefix="t19-static-"))
        self.addCleanup(lambda: shutil.rmtree(static_root, ignore_errors=True))
        with override_settings(
            STATIC_ROOT=str(static_root),
            STORAGES={"staticfiles": {
                "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
            }},
        ):
            call_command("collectstatic", interactive=False, verbosity=0)
        # The WhiteNoise manifest exists and the report_v2 assets were collected.
        self.assertTrue((static_root / "staticfiles.json").is_file())
        collected = [p.name for p in (static_root / "report_v2").iterdir() if p.is_file()]
        self.assertTrue(any(name.startswith("report.css") for name in collected), collected)
        self.assertTrue(any(name.startswith("print.css") for name in collected), collected)
        self.assertTrue(any(name.startswith("report.js") for name in collected), collected)

    # -- 5. nothing forbidden was added ----------------------------------------------------
    def test_no_pdf_engine_scheduler_or_attachment_workflow_was_added(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()
        for forbidden in ("weasyprint", "reportlab", "fpdf", "pdfkit", "xhtml2pdf",
                          "celery", "apscheduler", "croniter", "django-celery"):
            self.assertNotIn(forbidden, requirements)
        exports_source = Path("report_v2/exports.py").read_text(encoding="utf-8")
        self.assertNotIn("MIMEApplication", exports_source)          # no attachment workflow
        self.assertNotIn('Content-Disposition", "attachment"', exports_source)
        # Production modules only (this test's own docstring mentions the scan targets).
        production_sources = [
            path
            for path in Path("report_v2").rglob("*.py")
            if "tests" not in path.relative_to("report_v2").parts
        ]
        for source in production_sources:
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("celery", text.lower(), str(source))
            self.assertNotIn("crontab", text.lower(), str(source))
        for source in Path("report_v2/static/report_v2").rglob("*.js"):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("localStorage", text, str(source))
            self.assertNotIn("sessionStorage", text, str(source))

    # -- 6. the initial YAML: 17 widgets, seven display types, no text box -----------------
    def test_initial_seed_yaml_shape_matches_the_legacy_map(self):
        seed = Path("report_v2/seed/prime-overview.v1.yaml").read_text(encoding="utf-8")
        definition = load_report_definition(seed)
        widgets = [
            widget
            for section in definition.get("sections") or []
            for widget in section.get("widgets") or []
        ]
        self.assertEqual(len(widgets), 17)
        types = {widget.get("type") for widget in widgets}
        self.assertTrue(types <= _SEVEN_DISPLAYS, types)
        self.assertNotIn("text", types)          # the legacy monospaced text box is not migrated
        self.assertNotIn("textbox", types)
        # Every widget declares the disclosure flag the CSV/email rules key on.
        for widget in widgets:
            self.assertIn(widget.get("export"), ("full", "summary"), widget.get("id"))
