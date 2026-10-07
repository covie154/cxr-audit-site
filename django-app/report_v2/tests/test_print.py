# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 17 snapshot freeze + print flow: endpoint security and freeze guarantees.

Reuses the Task-13 page-test machinery (layout, synthetic row seam, scratch
``REPORT_V2_ROOT``) and adds a scratch snapshot store root per test. Every evaluated
row is synthetic (reserved accessions, SYNTH site codes); the ORM seam is monkeypatched
so no database table other than the auth users is ever read. No email is sent; no
clinical data is constructed.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from report_v2 import snapshots
from report_v2.tests.test_pages import LAYOUT, _SETTINGS, _Seam, _make_seam

LAYOUT_V2_TITLE = "Task 13 Report Republished"


class _Flow:
    """Shared helpers: publish, page-token harvest, snapshot POST, print GET."""

    def __init__(self, test: "PrintFlowTests"):
        self.test = test

    def publish(self, def_id: str, yaml_text: str = LAYOUT) -> str:
        client = Client(SERVER_NAME="localhost")
        client.force_login(self.test.admin)
        response = client.post(
            "/report/layout/editor/publish/", {"def_id": def_id, "yaml_text": yaml_text}
        )
        self.test.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()["version"]

    def tokens_from_page(self, client: Client, slug: str) -> dict[str, str]:
        response = client.get(f"/report/{slug}/")
        self.test.assertEqual(response.status_code, 200)
        page = response.content.decode("utf-8")
        tokens = {
            match.group(1): html.unescape(match.group(2))
            for match in re.finditer(
                r'data-widget-id="([^"]+)"[^>]*data-context-token="([^"]+)"', page
            )
        }
        self.test.assertEqual(set(tokens), {"v1", "t1", "v2"}, page[:200])
        return tokens

    def snapshot_body(self, tokens: dict[str, str], *, state_by_widget=None, settled=True) -> dict:
        state_by_widget = state_by_widget or {}
        widgets = []
        for widget_id, token in tokens.items():
            entry = {"context": token}
            entry.update(state_by_widget.get(widget_id) or {})
            widgets.append(entry)
        return {"settled": settled, "widgets": widgets}

    def post_snapshot(self, client: Client, slug: str, body: dict):
        client.get(f"/report/{slug}/")  # prime the csrftoken cookie
        # The page GET itself hydrates every widget (legitimate reads); zero out the
        # ledger so the assertions below measure only what the POST itself read.
        seam = getattr(self.test, "seam", None)
        if seam is not None:
            seam.reset()
        return client.post(
            f"/report/{slug}/snapshot/",
            json.dumps(body),
            content_type="application/json",
            headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        )


@override_settings(**_SETTINGS)
class PrintFlowTests(TestCase):
    """One named test per Task-17 done-when criterion."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="t17-admin", email="t17-admin@example.invalid", password="pw-strong-1"
        )
        cls.normal = User.objects.create_user(
            username="t17-normal", email="t17-normal@example.invalid", password="pw-strong-1"
        )
        cls.stranger = User.objects.create_user(
            username="t17-stranger", email="t17-stranger@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.defs_root = Path(tempfile.mkdtemp(prefix="t17-defs-"))
        defs_overrider = override_settings(REPORT_V2_ROOT=str(self.defs_root))
        defs_overrider.enable()
        self.addCleanup(defs_overrider.disable)
        self.snap_root = Path(tempfile.mkdtemp(prefix="t17-print-"))
        snap_overrider = override_settings(REPORT_V2_SNAPSHOT_ROOT=str(self.snap_root))
        snap_overrider.enable()
        self.addCleanup(snap_overrider.disable)
        snapshots._reset_store_for_tests()
        self.addCleanup(snapshots._reset_store_for_tests)
        self.addCleanup(lambda: shutil.rmtree(self.defs_root, ignore_errors=True))
        self.addCleanup(lambda: shutil.rmtree(self.snap_root, ignore_errors=True))
        self.flow = _Flow(self)
        self.seam = _make_seam()

    def _login(self, user, *, enforce_csrf: bool = False) -> Client:
        client = Client(SERVER_NAME="localhost", enforce_csrf_checks=enforce_csrf)
        client.force_login(user)
        return client

    def _patch_seam(self):
        patcher = mock.patch("report_v2.data.fetch_project_rows", self.seam)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create_snapshot(self, client: Client, slug: str, *, state_by_widget=None, settled=True):
        tokens = self.flow.tokens_from_page(client, slug)
        body = self.flow.snapshot_body(tokens, state_by_widget=state_by_widget, settled=settled)
        return self.flow.post_snapshot(client, slug, body)

    # -- 1. authentication ---------------------------------------------------------------
    def test_snapshot_and_print_require_login(self):
        anonymous = Client(SERVER_NAME="localhost")
        response = anonymous.post("/report/t13report/snapshot/", "{}", content_type="application/json")
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        response = anonymous.get("/report/t13report/print/whatever/")
        self.assertEqual(response.status_code, 302)

    # -- 2. CSRF is enforced on the freeze POST ------------------------------------------
    def test_snapshot_post_enforces_csrf(self):
        self._patch_seam()
        self.flow.publish("t13report")
        strict = self._login(self.normal, enforce_csrf=True)
        strict.get("/report/t13report/")  # prime cookie but withhold the header
        tokens = self.flow.tokens_from_page(strict, "t13report")
        self.seam.reset()  # page hydration is a legitimate read; measure only the POST
        body = self.flow.snapshot_body(tokens)
        response = strict.post(
            "/report/t13report/snapshot/", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.seam.calls, [])

    # -- 3. the pending gate blocks before a single row is read ---------------------------
    def test_pending_updates_block_the_export(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        for settled in (None, False):
            body = {"widgets": [{"context": "x"}]}
            if settled is not None:
                body["settled"] = settled
            response = self.flow.post_snapshot(client, "t13report", body)
            self.assertEqual(response.status_code, 409, response.content[:200])
            self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(self.seam.calls, [])

    # -- 4. every widget exports its own dates, filters, grouping and metadata ------------
    def test_print_shows_every_widget_state_and_metadata(self):
        self._patch_seam()
        version = self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(
            client, "t13report",
            state_by_widget={
                "v1": {"filters": {"site": "SYNTH-SITE-A"}, "comparison": "site"},
                "t1": {"date": {"relative": "D-7"}},
            },
        )
        self.assertEqual(response.status_code, 201, response.content[:400])
        print_url = response.json()["print_url"]
        self.assertTrue(print_url.startswith("/report/t13report/print/"))

        printed = client.get(print_url)
        self.assertEqual(printed.status_code, 200)
        self.assertIn("text/html", printed["Content-Type"])
        page = printed.content.decode("utf-8")
        # Report-level pinning.
        self.assertIn(version, page)
        self.assertIn("t13report", page)
        self.assertIn("prime", page)
        # Light export theme and the print stylesheet.
        self.assertIn('data-theme="light"', page)
        self.assertIn("print.css", page)
        # Per-widget dates / anchor / state / grouping.
        self.assertIn("Window", page)
        self.assertIn("2026-08-02 .. 2026-09-01", page)  # default D-30 window
        self.assertIn("2026-09-01", page)                # anchor D
        self.assertIn("site=SYNTH-SITE-A", page)
        self.assertIn("group by site", page)
        self.assertIn("window D-7", page)
        # Counts reconciliation and provenance.
        self.assertIn("matching 3 of 3 · 3 eligible for measurement", page)
        self.assertIn("record_count", page)
        self.assertIn("Threshold policy", page)
        # All three widgets printed, including the offscreen/never-matching one.
        for title in ("Value One", "Table One", "Never Matching"):
            self.assertIn(title, page)

    def test_time_grouping_survives_snapshot_freeze(self):
        self._patch_seam()
        layout = LAYOUT.replace("type: value", "type: line\n    bucket: week", 1)
        self.flow.publish("t13report", layout)
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report", state_by_widget={"v1": {"time_grouping": "month"}})
        self.assertEqual(response.status_code, 201, response.content[:400])
        document = snapshots.load_snapshot(response.json()["token"], user_id=self.normal.pk, project_id="prime", slug="t13report")
        widget = next(w for w in document["widgets"] if w["widget_id"] == "v1")
        self.assertEqual(widget["applied"]["time_grouping"], "month")
        self.assertTrue(all(b["size"] == "month" for b in widget["payload"]["buckets"]))

    def test_value_calendar_groups_and_relative_end_survive_snapshot(self):
        self.seam.good[0] = {**self.seam.good[0], "event_date": date(2026, 8, 24)}
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report", state_by_widget={
            "v1": {"time_grouping": "week", "date": {"start": "W-2", "end": "W"}}
        })
        self.assertEqual(response.status_code, 201, response.content[:400])
        document = snapshots.load_snapshot(response.json()["token"], user_id=self.normal.pk, project_id="prime", slug="t13report")
        widget = next(w for w in document["widgets"] if w["widget_id"] == "v1")
        self.assertEqual(widget["applied"]["date"], {"start": "W-2", "end": "W"})
        self.assertTrue(widget["payload"]["time_groups"])
        printed = client.get(response.json()["print_url"])
        self.assertEqual(printed.status_code, 200)
        self.assertIn(widget["payload"]["time_groups"][0]["label"], printed.content.decode())

    # -- 5. later data changes or publication do not alter the captured export ------------
    def test_print_is_frozen_against_data_and_publication_changes(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        self.assertEqual(response.status_code, 201)
        print_url = response.json()["print_url"]
        first = client.get(print_url)
        self.assertEqual(first.status_code, 200)
        self.assertIn("matching 3 of 3", first.content.decode("utf-8"))

        # (a) the dataset changes underneath: the print view must not re-evaluate.
        with mock.patch(
            "report_v2.data.fetch_project_rows", side_effect=AssertionError("print must not read rows")
        ):
            again = client.get(print_url)
            self.assertEqual(again.status_code, 200)
            self.assertIn("matching 3 of 3", again.content.decode("utf-8"))

        # (b) a new version is published underneath: the export keeps its pinned version.
        republished = LAYOUT.replace("title: Task 13 Report", f"title: {LAYOUT_V2_TITLE}")
        self.flow.publish("t13report", republished)
        after = client.get(print_url)
        self.assertEqual(after.status_code, 200)
        page = after.content.decode("utf-8")
        self.assertNotIn(LAYOUT_V2_TITLE, page)
        self.assertIn("t13report@r1", page)

    # -- 6. foreign snapshots fail explicitly ---------------------------------------------
    def test_print_rejects_foreign_user(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        print_url = response.json()["print_url"]
        stranger = self._login(self.stranger)
        denied = stranger.get(print_url)
        self.assertEqual(denied.status_code, 403)
        self.assertIn(b"another user", denied.content)

    # -- 7. expired snapshots regenerate explicitly (never silently re-frozen) ------------
    def test_print_expired_returns_regenerate_message(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        print_url = response.json()["print_url"]
        # Simulate the store aging the entry out: a fresh empty store root.
        empty_root = Path(tempfile.mkdtemp(prefix="t17-gone-"))
        self.addCleanup(lambda: shutil.rmtree(empty_root, ignore_errors=True))
        with override_settings(REPORT_V2_SNAPSHOT_ROOT=str(empty_root)):
            snapshots._reset_store_for_tests()
            try:
                expired = client.get(print_url)
            finally:
                snapshots._reset_store_for_tests()
        self.assertEqual(expired.status_code, 410)
        self.assertIn(b"regenerate", expired.content)

    # -- 8. tampered snapshot ids fail explicitly ------------------------------------------
    def test_print_tampered_token_fails(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        print_url = response.json()["print_url"]
        stem = print_url.rstrip("/")
        for mangled in (stem + "xx/", stem[:-2] + "!!/", "/report/t13report/print//"):
            denied = client.get(mangled)
            self.assertIn(denied.status_code, (403, 404))
            if denied.status_code == 403:
                self.assertIn(b"failed to verify", denied.content)

    # -- 9. the freeze must cover the published widget set exactly once -------------------
    def test_snapshot_requires_exact_widget_coverage(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        tokens = self.flow.tokens_from_page(client, "t13report")
        # Missing v2.
        partial = {"settled": True,
                   "widgets": [{"context": tokens[w]} for w in ("v1", "t1")]}
        response = self.flow.post_snapshot(client, "t13report", partial)
        self.assertEqual(response.status_code, 400)
        self.assertIn("exactly once", response.json()["error"])
        # Duplicated v1 in place of v2.
        dup = {"settled": True,
               "widgets": [{"context": tokens[w]} for w in ("v1", "t1", "v1")]}
        response = self.flow.post_snapshot(client, "t13report", dup)
        self.assertEqual(response.status_code, 400)
        # An entry without its signed context token is an explicit pre-row rejection
        # (fail-closed as tampered, exactly like the widget-data endpoint), never a 500.
        no_context = {"settled": True,
                      "widgets": [{"context": tokens["v1"]}, {"context": tokens["t1"]}, {}]}
        response = self.flow.post_snapshot(client, "t13report", no_context)
        self.assertIn(response.status_code, (400, 403))
        self.assertEqual(self.seam.calls, [])

    # -- 10. entries are validated exactly like the widget-data endpoint ------------------
    def test_snapshot_validates_entries_like_widget_data(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        tokens = self.flow.tokens_from_page(client, "t13report")
        # Disallowed filter dimension -> 400 before any row is read.
        bad_filter = {"settled": True, "widgets": [
            {"context": tokens["v1"], "filters": {"hosp": "x"}},
            {"context": tokens["t1"]}, {"context": tokens["v2"]},
        ]}
        response = self.flow.post_snapshot(client, "t13report", bad_filter)
        self.assertEqual(response.status_code, 400)
        # Garbage context token -> 403.
        garbage = {"settled": True, "widgets": [
            {"context": "not-a-token"}, {"context": tokens["t1"]}, {"context": tokens["v2"]},
        ]}
        response = self.flow.post_snapshot(client, "t13report", garbage)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.seam.calls, [])
        # A widget swapped between reports (context bound to another slug) -> 403.
        cross = {"settled": True, "widgets": [
            {"context": tokens["v1"]}, {"context": tokens["t1"]},
            {"context": signing_dumps("other|t13report@r1|v2")},
        ]}
        response = self.flow.post_snapshot(client, "t13report", cross)
        self.assertIn(response.status_code, (403, 409))
        self.assertEqual(self.seam.calls, [])
        # Stale pinned version after a republish -> 409, before any row is read.
        self.flow.publish("t13report", LAYOUT.replace("title: Task 13 Report",
                                                      f"title: {LAYOUT_V2_TITLE}"))
        stale = {"settled": True, "widgets": [{"context": tokens[w]} for w in ("v1", "t1", "v2")]}
        response = self.flow.post_snapshot(client, "t13report", stale)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["status"], "stale")
        self.assertEqual(self.seam.calls, [])

    # -- 11. a snapshot is never restored as user preferences ------------------------------
    def test_print_page_carries_no_page_state_contract(self):
        self._patch_seam()
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        page = client.get(response.json()["print_url"]).content.decode("utf-8")
        for absent in ("data-report-page", "data-context-token", "widget-controls",
                       "data-data-url", "data-initial-payload"):
            self.assertNotIn(absent, page)
        # The report page itself still renders its normal defaults afterwards.
        fresh = client.get("/report/t13report/")
        self.assertEqual(fresh.status_code, 200)
        self.assertIn(b"data-report-page", fresh.content)

    # -- 12. oversized tables paginate and widget faults freeze as visible errors ----------
    def test_oversized_table_note_and_frozen_widget_errors(self):
        many = _Seam(good=[
            {"accession": 9_000_000 + i, "event_date": date(2026, 9, 1),
             "site": "SYNTH-SITE-A", "eligible": True}
            for i in range(60)
        ], error_ids={"v2"})
        patcher = mock.patch("report_v2.data.fetch_project_rows", many)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.flow.publish("t13report")
        client = self._login(self.normal)
        response = self._create_snapshot(client, "t13report")
        self.assertEqual(response.status_code, 201)
        page = client.get(response.json()["print_url"]).content.decode("utf-8")
        self.assertIn("Table pagination", page)      # long tables handled, not clipped silently
        self.assertIn("more rows", page)
        self.assertIn("could not be evaluated", page)  # the faulting widget froze its error
        self.assertIn("synthetic adapter fault", page)


def signing_dumps(payload: str) -> str:
    """A correctly signed context token for a *foreign* binding (salt reused on purpose)."""
    from django.core import signing
    return signing.dumps(payload, salt="report_v2.page_context.v1")
