# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 17 transient render-snapshot store: scoping, expiry, tampering and bounds.

Every test runs the file-backed store under a scratch ``REPORT_V2_SNAPSHOT_ROOT`` (the
process-wide cache handle is reset around each test so the override always binds). No
database, no ORM, no clinical data: the frozen documents below are synthetic maps.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.core import signing
from django.test import SimpleTestCase, override_settings

from report_v2 import snapshots

_SETTINGS = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)

_DOCUMENT = {
    "kind": "report_v2_print_v1",
    "project_id": "prime",
    "slug": "t17report",
    "version": "t17report@r1",
    "title": "Task 17 Report",
    "generated": "2026-09-21T00:00:00+00:00",
    "widgets": [
        {"widget_id": "v1", "title": "Value One", "type": "value",
         "applied": {"date": None, "filters": {"site": "SYNTH-SITE-A"},
                     "comparison": "site", "page": 1},
         "payload": {"counts": {"matching": 3}}},
    ],
}


def _create(**overrides):
    kwargs = dict(user_id=7, project_id="prime", slug="t17report", document=_DOCUMENT)
    kwargs.update(overrides)
    return snapshots.create_snapshot(**kwargs)


@override_settings(**_SETTINGS)
class SnapshotStoreTests(SimpleTestCase):
    """One named test per Task-17 store guarantee."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="t17-snaps-"))
        overrider = override_settings(REPORT_V2_SNAPSHOT_ROOT=str(self.root))
        overrider.enable()
        self.addCleanup(overrider.disable)
        # Bind a fresh store handle to the scratch root, and drop it again afterwards
        # so no other test inherits this root.
        snapshots._reset_store_for_tests()
        self.addCleanup(snapshots._reset_store_for_tests)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    # -- 1. roundtrip: create then load returns exactly the frozen document -------------
    def test_roundtrip_returns_the_frozen_document_unchanged(self):
        token = _create()
        loaded = snapshots.load_snapshot(
            token, user_id=7, project_id="prime", slug="t17report"
        )
        self.assertEqual(loaded, _DOCUMENT)  # nothing injected, nothing restorable as state
        # The store lives under the configured private root, never an arbitrary path.
        entries = [p for p in self.root.rglob("*") if p.is_file()]
        self.assertTrue(entries, "the file-backed store must write under its root")

    # -- 2. tampered token ---------------------------------------------------------------
    def test_tampered_token_fails_explicitly(self):
        token = _create()
        for mangled in ("", "garbage", token[:-2] + "xx", token + "x"):
            with self.assertRaises(snapshots.SnapshotTamperedError):
                snapshots.load_snapshot(
                    mangled, user_id=7, project_id="prime", slug="t17report"
                )

    # -- 3. foreign scope: user / project / slug ------------------------------------------
    def test_foreign_user_project_or_slug_fails(self):
        token = _create()
        with self.assertRaises(snapshots.SnapshotForeignError):
            snapshots.load_snapshot(token, user_id=8, project_id="prime", slug="t17report")
        with self.assertRaises(snapshots.SnapshotForeignError):
            snapshots.load_snapshot(token, user_id=7, project_id="other", slug="t17report")
        with self.assertRaises(snapshots.SnapshotForeignError):
            snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="otherreport")

    # -- 4. expiry: signed claim, store timeout and eviction all regenerate explicitly ----
    def test_expired_snapshots_fail_with_regenerate_message(self):
        # (a) signed expiry in the past
        past = time.time() - 10
        stale = signing.dumps(
            {"sid": "abc", "u": 7, "p": "prime", "r": "t17report", "x": past},
            salt="report_v2.snapshot.v1",
        )
        with self.assertRaises(snapshots.SnapshotExpiredError) as ctx:
            snapshots.load_snapshot(stale, user_id=7, project_id="prime", slug="t17report")
        self.assertIn("regenerate", str(ctx.exception))
        # (b) valid signature but the store entry timed out / was evicted
        token = _create()
        sid = signing.loads(token, salt="report_v2.snapshot.v1")["sid"]
        snapshots._store().delete(f"snap:{sid}")
        with self.assertRaises(snapshots.SnapshotExpiredError) as ctx:
            snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="t17report")
        self.assertIn("regenerate", str(ctx.exception))

    # -- 5. store entry that disagrees with its token is tampering ------------------------
    def test_store_entry_token_mismatch_is_tampering(self):
        token = _create()
        claims = signing.loads(token, salt="report_v2.snapshot.v1")
        key = f"snap:{claims['sid']}"
        stored = {
            "sid": claims["sid"], "user_id": 999, "project_id": "prime",
            "slug": "t17report", "created": 0, "expires": time.time() + 600,
            "document": _DOCUMENT,
        }
        import json as _json
        snapshots._store().set(key, _json.dumps(stored), timeout=600)
        with self.assertRaises(snapshots.SnapshotTamperedError):
            snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="t17report")

    # -- 6. size and count bounds refuse before anything is written -----------------------
    def test_payload_bounds_are_enforced(self):
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(document={"widgets": []})  # empty widget list
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(document={"widgets": [{"widget_id": f"w{i}"} for i in range(65)]})
        huge = dict(_DOCUMENT, widgets=[
            {"widget_id": f"w{i}", "blob": "x" * 100_000} for i in range(50)
        ])
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(document=huge)  # > 4 MB
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(document={"widgets": [{"widget_id": "w", "bad": object()}]})  # not JSON
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(ttl=5)  # below the minimum retention bound
        with self.assertRaises(snapshots.SnapshotPayloadError):
            _create(ttl=999_999)  # above the maximum retention bound

    # -- 7. default root is the private_data tree, never a public/static location ---------
    def test_default_root_is_private_and_configurable(self):
        with override_settings(REPORT_V2_SNAPSHOT_ROOT=""):
            from django.conf import settings as dj_settings
            base = Path(str(dj_settings.BASE_DIR))
            expected = base.joinpath("private_data", "report_v2_snapshots")
            self.assertEqual(snapshots.default_snapshot_root(), expected)
        self.assertEqual(snapshots.default_snapshot_root(), self.root)

    # -- 8. ids are opaque: no user/path/row material leaks into the token ----------------
    def test_opaque_token_carries_no_document_material(self):
        token = _create()
        self.assertNotIn("SYNTH-SITE-A", token)
        claims = signing.loads(token, salt="report_v2.snapshot.v1")
        self.assertEqual(set(claims), {"sid", "u", "p", "r", "x"})

    # -- 9. two snapshots coexist independently -------------------------------------------
    def test_snapshots_are_independent(self):
        other = dict(_DOCUMENT, version="t17report@r2")
        token_a = _create()
        token_b = _create(document=other)
        self.assertNotEqual(token_a, token_b)
        self.assertEqual(
            snapshots.load_snapshot(token_b, user_id=7, project_id="prime", slug="t17report")["version"],
            "t17report@r2",
        )

    # -- 10. wall-clock is read at call time, not frozen at import -------------------------
    def test_expiry_uses_call_time(self):
        token = _create()
        later = time.time() + snapshots.DEFAULT_SNAPSHOT_TTL + 5
        with mock.patch("report_v2.snapshots.time.time", return_value=later):
            with self.assertRaises(snapshots.SnapshotExpiredError):
                snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="t17report")

    # -- 11. the document itself is plain data (json round-trips byte-stable) -------------
    def test_document_is_plain_data(self):
        import json
        token = _create()
        loaded = snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="t17report")
        self.assertEqual(json.loads(json.dumps(loaded)), loaded)

    # -- 12. load performs no writes (read-only verification path) -------------------------
    def test_load_performs_no_writes(self):
        token = _create()
        before = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        snapshots.load_snapshot(token, user_id=7, project_id="prime", slug="t17report")
        after = sorted(str(p) for p in self.root.rglob("*") if p.is_file())
        self.assertEqual(before, after)
