# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 18 snapshot-based HTML email: validation, disclosure rules and send guarantees.

Reuses the Task-13 synthetic seam/scratch-root machinery. The email backend is locmem:
no real message is ever sent. Every evaluated row is synthetic (reserved accessions,
SYNTH site codes); chart images are hand-built PNG-signature byte strings.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.core import mail
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from report_v2 import snapshots
from report_v2.tests.test_pages import _SETTINGS, _Seam, _rows

# Four widgets: a value widget, a chart-typed (pie) widget for the image contract, a
# summary-only table (the discrepancy-case disclosure rule) and a full-export table.
LAYOUT = """\
schema_version: 1
project: prime
id: t18report
title: Task 18 Report
grid:
  columns: 12
  row_height_px: 64
sections:
- id: s1
  title: Section One
  widgets:
  - id: v1
    title: Value One
    type: value
    layout:
      width: 4
      height: 1
    query:
      measurement: record_count
      inputs: {}
    window:
      start: D-30
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
  - id: c1
    title: Share Pie
    type: pie
    layout:
      width: 4
      height: 2
    query:
      measurement: record_count
      inputs: {}
    window:
      start: D-30
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
  - id: t1
    title: Discrepancy Table
    type: table
    layout:
      width: 6
      height: 4
    query:
      measurement: record_count
      inputs: {}
    window:
      start: D-30
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: summary
  - id: t2
    title: Full Table
    type: table
    layout:
      width: 6
      height: 4
    query:
      measurement: record_count
      inputs: {}
    window:
      start: D-30
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
"""

_WIDGET_IDS = {"v1", "c1", "t1", "t2"}

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-chart-bytes" * 4


def _png_data_url(payload: bytes = _PNG_BYTES) -> str:
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


@override_settings(**_SETTINGS)
class EmailFlowTests(TestCase):
    """One named test per Task-18 done-when criterion."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="t18-admin", email="t18-admin@example.invalid", password="pw-strong-1"
        )
        cls.normal = User.objects.create_user(
            username="t18-normal", email="t18-normal@example.invalid", password="pw-strong-1"
        )
        cls.stranger = User.objects.create_user(
            username="t18-stranger", email="t18-stranger@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.defs_root = Path(tempfile.mkdtemp(prefix="t18-defs-"))
        defs_overrider = override_settings(REPORT_V2_ROOT=str(self.defs_root))
        defs_overrider.enable()
        self.addCleanup(defs_overrider.disable)
        self.snap_root = Path(tempfile.mkdtemp(prefix="t18-mail-"))
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
        self._publish()

    # -- helpers -----------------------------------------------------------
    def _publish(self, yaml_text: str = LAYOUT) -> str:
        client = Client(SERVER_NAME="localhost")
        client.force_login(self.admin)
        response = client.post(
            "/report/layout/editor/publish/", {"def_id": "t18report", "yaml_text": yaml_text}
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()["version"]

    def _login(self, user, *, enforce_csrf: bool = False) -> Client:
        client = Client(SERVER_NAME="localhost", enforce_csrf_checks=enforce_csrf)
        client.force_login(user)
        return client

    def _snapshot_token(self, client: Client) -> str:
        page = client.get("/report/t18report/").content.decode("utf-8")
        tokens = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r'data-widget-id="([^"]+)"[^>]*data-context-token="([^"]+)"', page
            )
        }
        self.assertEqual(set(tokens), _WIDGET_IDS)
        body = {
            "settled": True,
            "widgets": [
                {"context": tokens[widget_id], "filters": {"site": "SYNTH-SITE-A"}}
                for widget_id in sorted(tokens)
            ],
        }
        response = client.post(
            "/report/t18report/snapshot/", json.dumps(body), content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(response.status_code, 201, response.content[:400])
        return response.json()["token"]

    def _email(self, client: Client, token: str, **overrides) -> object:
        body = {
            "snapshot": token,
            "recipients": ["clinician@example.invalid"],
            "note": "",
            "images": {},
        }
        body.update(overrides)
        return client.post(
            "/report/t18report/email/", json.dumps(body), content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )

    def _parts(self, message) -> tuple[str, str]:
        """The (plain-text, html) bodies of the sent message."""
        text_html = ""
        text_plain = ""
        for part in message.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not text_plain:
                text_plain = part.get_payload(decode=True).decode("utf-8")
            elif ctype == "text/html" and not text_html:
                text_html = part.get_payload(decode=True).decode("utf-8")
        return text_plain, text_html

    # -- 1. authentication + explicit action ---------------------------------------------
    def test_email_requires_login_and_is_post_only(self):
        anonymous = Client(SERVER_NAME="localhost")
        response = anonymous.post("/report/t18report/email/", "{}", content_type="application/json")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        client = self._login(self.normal)
        client.get("/report/t18report/")
        self.assertEqual(client.get("/report/t18report/email/").status_code, 405)

    def test_email_enforces_csrf(self):
        strict = self._login(self.normal, enforce_csrf=True)
        strict.get("/report/t18report/")  # prime the cookie but withhold the header
        response = strict.post(
            "/report/t18report/email/", "{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_preview_and_print_never_send(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        client.get(f"/report/t18report/print/{token}/")
        self.assertEqual(len(mail.outbox), 0)

    # -- 2. a correct send carries every intended widget + metadata ----------------------
    def test_email_sends_snapshot_values_recipients_note_and_cid_images(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        response = self._email(
            client, token,
            recipients=["a@example.invalid", "b@example.invalid"],
            note="Please review the weekly numbers.",
            images={"c1": _png_data_url()},
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(response.json()["status"], "sent")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["a@example.invalid", "b@example.invalid"])
        self.assertIn("Task 18 Report", message.subject)
        self.assertIn("t18report@r1", message.subject)

        text_plain, text_html = self._parts(message.message())
        # Every intended widget, its window/state/counts and provenance metadata.
        for title in ("Value One", "Share Pie", "Discrepancy Table", "Full Table"):
            self.assertIn(title, text_html)
            self.assertIn(title, text_plain)
        self.assertIn("02/08/2026 .. 01/09/2026", text_html)
        self.assertIn("site=SYNTH-SITE-A", text_html)
        self.assertIn("matching 3 of 3", text_html)
        self.assertIn("record_count", text_html)
        self.assertIn("threshold policy", text_html)
        # The note and the CID reference.
        self.assertIn("Please review the weekly numbers.", text_html)
        self.assertIn('src="cid:c1@primer-llm"', text_html)
        self.assertIn("Note from the sender:", text_plain)
        # The inline image part exists with the right Content-ID.
        image_parts = [p for p in message.message().walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(image_parts), 1)
        self.assertEqual(image_parts[0]["Content-ID"], "<c1@primer-llm>")
        self.assertEqual(image_parts[0].get_payload(decode=True), _PNG_BYTES)
        # Readable prose fallback, not a monospaced dump and not a bare pointer.
        self.assertIn("Sent via PRIMER-LLM by t18-normal.", text_plain)
        self.assertIn("Window 02/08/2026 .. 01/09/2026", text_plain)
        self.assertNotIn("See HTML version", text_plain)

    def test_email_values_come_from_the_snapshot_not_later_data(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        # The dataset moves on (and the seam would explode): the email must still
        # carry the frozen numbers -- nothing re-evaluates on the email path.
        with mock.patch(
            "report_v2.data.fetch_project_rows", side_effect=AssertionError("email must not read rows")
        ):
            response = self._email(client, token)
        self.assertEqual(response.status_code, 200)
        _, text_html = self._parts(mail.outbox[0].message())
        self.assertIn("matching 3 of 3", text_html)

    # -- 3. disclosure rules --------------------------------------------------------------
    def test_case_tables_are_summary_only_and_full_tables_are_capped(self):
        client = self._login(self.normal)
        self.seam.good = _rows(60)
        token = self._snapshot_token(client)
        response = self._email(client, token)
        self.assertEqual(response.status_code, 200)
        _, text_html = self._parts(mail.outbox[0].message())
        # Summary-only table: counts yes, accession case rows no.
        self.assertIn("summary-only in email", text_html)
        for widget_html in re.findall(r"Discrepancy Table.*?</div>", text_html, re.S):
            self.assertNotIn("9000000", widget_html)
        # Full-export table: rows appear, capped at the first 25 of the captured page.
        self.assertIn("9000000", text_html)
        self.assertIn("Showing the first 25 of 50 captured rows.", text_html)

    def test_note_free_text_is_escaped_in_the_html_body(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        response = self._email(client, token, note="<script>alert('x')</script>")
        self.assertEqual(response.status_code, 200)
        _, text_html = self._parts(mail.outbox[0].message())
        self.assertNotIn("<script>", text_html)
        self.assertIn("&lt;script&gt;", text_html)

    # -- 4. image validation --------------------------------------------------------------
    def test_chart_images_are_validated_against_the_snapshot(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        cases = [
            {"images": {"nope": _png_data_url()}},                     # not a snapshot widget
            {"images": {"v1": _png_data_url()}},                       # not a chart-typed widget
            {"images": {"c1": "data:image/jpeg;base,AAAA"}},           # wrong MIME
            {"images": {"c1": "data:image/png;base64,!!!!"}},          # invalid base64
            {"images": {"c1": _png_data_url(b"GIF89a" + b"x" * 64)}},  # not PNG content
            {"images": {"c1": _png_data_url(b"\x89PNG\r\n\x1a\n" + b"x" * 600_000)}},  # oversized
        ]
        for override in cases:
            response = self._email(client, token, **override)
            self.assertEqual(response.status_code, 400, response.content[:200])
        self.assertEqual(len(mail.outbox), 0)

    # -- 5. recipient / note validation ----------------------------------------------------
    def test_recipients_and_note_are_validated_and_bounded(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        for override in (
            {"recipients": []},
            {"recipients": "a@example.invalid"},                       # must be a list
            {"recipients": ["not-an-email"]},
            {"recipients": ["a@b.invalid"] * 21},                      # count bound
            {"note": "x" * 2001},
            {"note": 42},
        ):
            response = self._email(client, token, **override)
            self.assertEqual(response.status_code, 400, override)
        self.assertEqual(len(mail.outbox), 0)
        # Deduplication keeps one copy per address.
        response = self._email(client, token, recipients=["a@b.invalid", "a@b.invalid"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[0].to, ["a@b.invalid"])

    # -- 6. snapshot scope failures --------------------------------------------------------
    def test_expired_foreign_or_tampered_snapshots_fail_explicitly(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        # Tampered token.
        response = self._email(client, token + "xx")
        self.assertEqual(response.status_code, 403)
        # Foreign user.
        stranger = self._login(self.stranger)
        stranger.get("/report/t18report/")
        response = self._email(stranger, token)
        self.assertEqual(response.status_code, 403)
        # Expired store entry.
        empty_root = Path(tempfile.mkdtemp(prefix="t18-gone-"))
        self.addCleanup(lambda: shutil.rmtree(empty_root, ignore_errors=True))
        with override_settings(REPORT_V2_SNAPSHOT_ROOT=str(empty_root)):
            snapshots._reset_store_for_tests()
            try:
                response = self._email(client, token)
            finally:
                snapshots._reset_store_for_tests()
        self.assertEqual(response.status_code, 410)
        self.assertIn("regenerate", response.json()["error"])
        self.assertEqual(len(mail.outbox), 0)

    # -- 7. duplicate-click prevention -----------------------------------------------------
    def test_duplicate_submission_is_rejected_without_resending(self):
        client = self._login(self.normal)
        token = self._snapshot_token(client)
        first = self._email(client, token, note="same note")
        self.assertEqual(first.status_code, 200)
        second = self._email(client, token, note="same note")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(len(mail.outbox), 1)
        # A different recipient list is a new, legitimate submission.
        third = self._email(client, token, recipients=["other@example.invalid"], note="same note")
        self.assertEqual(third.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

    # -- 8. request errors preserve the report --------------------------------------------
    def test_failed_email_keeps_the_report_page_working(self):
        client = self._login(self.normal)
        self._snapshot_token(client)
        failed = self._email(client, "garbage-token")   # tampered snapshot -> explicit 403
        self.assertEqual(failed.status_code, 403)
        page = client.get("/report/t18report/")
        self.assertEqual(page.status_code, 200)          # the live report is untouched
        self.assertIn(b"data-report-page", page.content)

    # -- 9. no persisted preferences --------------------------------------------------------
    def test_email_client_code_uses_no_storage_api(self):
        source = Path("report_v2/static/report_v2/report.js").read_text(encoding="utf-8")
        # Mirrors the node harness rule: no storage APIs, no cookie WRITES (the CSRF
        # helper's read-only `document.cookie` access is the sanctioned house idiom).
        for forbidden in ("localStorage", "sessionStorage", "indexedDB", "document.cookie ="):
            self.assertNotIn(forbidden, source)

    def test_page_carries_the_email_affordance_and_modal(self):
        client = self._login(self.normal)
        page = client.get("/report/t18report/").content.decode("utf-8")
        self.assertIn('data-action="email"', page)
        self.assertIn('<dialog class="email-modal-card" data-role="email-modal"', page)
        self.assertIn('data-role="email-recipients"', page)
