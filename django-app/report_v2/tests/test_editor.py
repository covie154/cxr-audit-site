# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 12 admin YAML editor: security, publish-integrity and preview-isolation guarantees.

Every filesystem touch goes through an injected scratch ``REPORT_V2_ROOT`` (never the real
``private_data`` tree, never ``~/serverfiles/downloads/db_2026-06-18.sqlite3``), and the only database
used is Django's own in-memory *test* database created by the runner. Each named test maps to one
Done-when criterion of the task.
"""
from __future__ import annotations

import inspect
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import Resolver404, resolve, reverse

from report_v2 import admin_views as av
from report_v2 import views
from report_v2.definitions.repository import DefinitionRepository, DraftNotFoundError, default_root

# Synthetic, non-clinical fixtures reused verbatim in spirit from Task 11: a minimal valid report and a
# YAML that the strict loader (anchors) rejects. Neither carries any clinical identifier.
VALID_YAML = """\
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

INVALID_YAML = """\
schema_version: 1
project: prime
id: bad
title: [&anchor "x"]
sections: []
"""

_MUTATION_PATHS = {
    "save": "/report/layout/editor/save/",
    "preview": "/report/layout/editor/preview/",
    "publish": "/report/layout/editor/publish/",
    "new": "/report/layout/editor/new/",
}

_SETTINGS = dict(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
    SECURE_SSL_REDIRECT=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)


@override_settings(**_SETTINGS)
class EditorAdminSecurityTests(TestCase):
    """One named test per Task-12 Done-when item; all state under a scratch root."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="editor-admin", email="editor-admin@example.invalid", password="pw-strong-1"
        )
        cls.normal = User.objects.create_user(
            username="editor-normal", email="editor-normal@example.invalid", password="pw-strong-1"
        )

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="t12-editor-"))
        overrider = override_settings(REPORT_V2_ROOT=str(self.root))
        overrider.enable()
        self.addCleanup(overrider.disable)
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        mail.outbox.clear()
        self.addCleanup(mail.outbox.clear)

    # -- helpers -----------------------------------------------------------
    def _repo(self) -> DefinitionRepository:
        # Fresh instance every call so assertions read the on-disk truth, not a cache.
        return DefinitionRepository(default_root(), project_id="prime")

    def _client(self, *, enforce_csrf=False):
        return Client(SERVER_NAME="localhost", enforce_csrf_checks=enforce_csrf)

    def _as_admin(self, *, enforce_csrf=False):
        client = self._client(enforce_csrf=enforce_csrf)
        client.force_login(self.admin)
        return client

    # -- 1. the editor + every mutation endpoint refuse non-admins -------
    def test_non_admin_cannot_access_editor(self):
        """Anonymous + normal users get 403/redirect (never 200) for the page AND every direct POST."""
        # Anonymous through the full HTTP stack.
        anon = self._client(enforce_csrf=True)
        page = anon.get("/report/layout/")
        self.assertEqual(page.status_code, 302)
        self.assertIn("/login", page.url)
        for label, url in _MUTATION_PATHS.items():
            with self.subTest(user="anonymous", endpoint=label):
                response = anon.post(url, {"def_id": "forbidden", "yaml_text": VALID_YAML})
                self.assertNotEqual(response.status_code, 200)
                self.assertIn(response.status_code, (302, 403))

        # Authenticated non-admin through the full HTTP stack.
        normal = self._as_user_client(self.normal, enforce_csrf=True)
        page = normal.get("/report/layout/")
        self.assertEqual(page.status_code, 403)
        for label, url in _MUTATION_PATHS.items():
            with self.subTest(user="normal", endpoint=label):
                response = normal.post(url, {"def_id": "forbidden", "yaml_text": VALID_YAML})
                self.assertEqual(response.status_code, 403)

        # A hand-crafted direct request (bypassing the client) is rejected by the gate itself,
        # BEFORE any model/filesystem work -- proven by the scratch root staying empty for that def_id.
        rf = RequestFactory(SERVER_NAME="localhost")
        for user in (AnonymousUser(), self.normal):
            for label, view in (
                ("save", av.editor_save_draft),
                ("preview", av.editor_preview),
                ("publish", av.editor_publish),
                ("new", av.editor_new),
            ):
                with self.subTest(user=type(user).__name__, endpoint=label):
                    request = rf.post(_MUTATION_PATHS[label], {"def_id": "forbidden", "yaml_text": VALID_YAML})
                    request.user = user
                    response = view(request)
                    self.assertNotEqual(response.status_code, 200)
                    self.assertIn(response.status_code, (302, 403))
        # No draft/blob/pointer was ever produced for the rejected def_id.
        self.assertFalse(any(self.root.rglob("*forbidden*")))

    def _as_user_client(self, user, *, enforce_csrf=False):
        client = self._client(enforce_csrf=enforce_csrf)
        client.force_login(user)
        return client

    # -- 2. CSRF is enforced on the mutators -----------------------------
    def test_missing_csrf_rejected(self):
        """A logged-in admin POST without a CSRF token is rejected (4xx) by the CSRF layer."""
        for label in ("save", "preview", "publish"):
            client = self._as_admin(enforce_csrf=True)
            with self.subTest(endpoint=label):
                response = client.post(_MUTATION_PATHS[label], {"def_id": "csrf", "yaml_text": VALID_YAML})
                self.assertGreaterEqual(response.status_code, 400)
                self.assertLess(response.status_code, 500)

    def test_bad_csrf_token_rejected(self):
        """Even a supplied-but-wrong token cannot bypass the CSRF protection."""
        client = self._as_admin(enforce_csrf=True)
        client.get("/report/layout/")  # establish a csrftoken cookie
        token = client.cookies.get("csrftoken")
        # Sanity: the editor page handed the admin a CSRF cookie at all.
        self.assertIsNotNone(token)
        response = client.post(
            _MUTATION_PATHS["save"],
            {"def_id": "csrf", "yaml_text": VALID_YAML, "csrfmiddlewaretoken": "x" * 64},
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertLess(response.status_code, 500)

    # -- 3. invalid YAML can never replace published content -------------
    def test_invalid_yaml_does_not_replace_published(self):
        """Publish valid content, then a rejected publish leaves the pointer byte-for-byte unchanged."""
        repo = self._repo()
        good = self._as_admin()
        first = good.post(_MUTATION_PATHS["publish"], {"def_id": "guarded", "yaml_text": VALID_YAML})
        self.assertEqual(first.status_code, 200)
        pointer_before = self._repo()._read_pointer("guarded")
        self.assertIsNotNone(pointer_before)

        bad = self._as_admin()
        rejected = bad.post(_MUTATION_PATHS["publish"], {"def_id": "guarded", "yaml_text": INVALID_YAML})
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("errors", rejected.json())
        self.assertTrue(rejected.json()["errors"])

        # Read the pointer back from a fresh repository instance -- unchanged.
        self.assertEqual(self._repo()._read_pointer("guarded"), pointer_before)

    # -- 4. preview neither publishes nor mails --------------------------
    def test_preview_does_not_publish_or_send_mail(self):
        """Preview of VALID and INVALID YAML: no pointer, no draft, and mail.outbox stays empty."""
        self.assertIsNone(self._repo()._read_pointer("previewer"))
        for label, yaml_text in (("valid", VALID_YAML), ("invalid", INVALID_YAML)):
            client = self._as_admin()
            with self.subTest(case=label):
                response = client.post(
                    _MUTATION_PATHS["preview"], {"def_id": "previewer", "yaml_text": yaml_text}
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("errors", payload)
                if label == "invalid":
                    self.assertFalse(payload["valid"])
                    self.assertTrue(payload["errors"])
                # Nothing was published and nothing was mailed.
                self.assertIsNone(self._repo()._read_pointer("previewer"))
                with self.assertRaises(DraftNotFoundError):
                    self._repo().read_draft("previewer")
                self.assertEqual(len(mail.outbox), 0)

    # -- 5. draft round-trip + optimistic-conflict without clobber -------
    def test_save_draft_and_stale_conflict(self):
        """A stale expected_revision yields 409 and the stored draft is not clobbered."""
        client = self._as_admin()
        saved = client.post(
            _MUTATION_PATHS["save"], {"def_id": "concurrent", "yaml_text": VALID_YAML}
        )
        self.assertEqual(saved.status_code, 200)
        rev1 = saved.json()["revision"]
        self.assertEqual(self._repo().read_draft("concurrent")[0], VALID_YAML)

        # A concurrent writer advances the draft behind the client's back.
        advanced = VALID_YAML.replace("title: T", "title: T-advanced")
        self._repo().save_draft("concurrent", advanced, expected_revision=None)

        # The original client now saves with its now-STALE revision: conflict, no clobber.
        stale = self._as_admin()
        conflict = stale.post(
            _MUTATION_PATHS["save"],
            {"def_id": "concurrent", "yaml_text": "attempted-clobber: yes", "expected_revision": rev1},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["status"], "conflict")
        # The on-disk draft is the concurrent writer's text, not the attempted clobber.
        self.assertEqual(self._repo().read_draft("concurrent")[0], advanced)

    # -- 6. admins can create independent reports ------------------------
    def test_admin_can_create_second_report(self):
        """editor_new yields independent reports whose publication pointers never collide."""
        one = self._as_admin()
        created_a = one.post(_MUTATION_PATHS["new"], {"def_id": "report-a"})
        self.assertEqual(created_a.status_code, 200)
        two = self._as_admin()
        created_b = two.post(_MUTATION_PATHS["new"], {"def_id": "report-b"})
        self.assertEqual(created_b.status_code, 200)

        # Neither started published.
        self.assertIsNone(self._repo()._read_pointer("report-a"))
        self.assertIsNone(self._repo()._read_pointer("report-b"))

        # Publish A only; B stays independent.
        pub = self._as_admin()
        published = pub.post(_MUTATION_PATHS["publish"], {"def_id": "report-a", "yaml_text": VALID_YAML})
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["version"], "report-a@r1")
        self.assertEqual(self._repo()._read_pointer("report-a"), "report-a@r1")
        self.assertIsNone(self._repo()._read_pointer("report-b"))

        # Republishing A does not touch B's (still-absent) pointer.
        again = self._as_admin()
        republished = again.post(_MUTATION_PATHS["publish"], {"def_id": "report-a", "yaml_text": VALID_YAML})
        self.assertEqual(republished.json()["version"], "report-a@r2")
        self.assertEqual(self._repo()._read_pointer("report-a"), "report-a@r2")
        self.assertIsNone(self._repo()._read_pointer("report-b"))

    # -- 7. the reserved route wins before any slug ----------------------
    def test_editor_route_before_slug(self):
        """'/report/layout/' resolves to the editor with no slug kwargs; legacy routes are intact."""
        match = resolve("/report/layout/")
        self.assertIs(match.func, av.editor)
        self.assertEqual(match.kwargs, {})  # not captured as a slug/def_id pattern

        # The report index still routes to the legacy v2 index view, and every named editor route
        # reverses inside the reserved /report/layout/ block (distinct names, none shadowed).
        self.assertIs(resolve("/report/").func, views.index)
        self.assertEqual(resolve("/report/layout/").url_name, "editor")
        for name in ("editor_save_draft", "editor_preview", "editor_publish", "editor_new"):
            with self.subTest(name=name):
                self.assertTrue(reverse(f"report_v2:{name}").startswith("/report/layout/"))

        # A stray slug path is NOT swallowed by the reserved block (still 404, i.e. no catch-all
        # was added and the legacy report lives on its own separate /report-old/ mount).
        with self.assertRaises(Resolver404):
            resolve("/report/some-random-slug/")

        # The admin page itself renders 200 through the full stack (proves the base-template
        # inheritance and the static assets actually resolve).
        page = self._as_admin().get("/report/layout/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Report layout", page.content.decode())

    # -- 8. no pointer-reordering (drag-and-drop) editing was added ------
    def test_no_drag_and_drop(self):
        """Source-level guard: the shipped editor assets introduce no DnD handlers/attributes."""
        targets = [
            Path(av.__file__),
            Path(__file__).parent.parent / "templates" / "report_v2" / "layout.html",
            Path(__file__).parent.parent / "templates" / "report_v2" / "_editor_form.html",
            Path(__file__).parent.parent / "static" / "report_v2" / "editor.js",
            Path(__file__).parent.parent / "static" / "report_v2" / "editor.css",
        ]
        forbidden = (
            "draggable", "ondrag", "ondrop", "ondragstart", "ondragover", "ondragend",
            "addeventlistener('drag", 'addeventlistener("drag', "setdata(", "getdata(", "dropeffect",
            "drag-", "drag_", "grab", "dragover",
        )
        for target in targets:
            self.assertTrue(target.exists(), f"missing deliverable: {target}")
            text = target.read_text(encoding="utf-8").lower()
            for token in forbidden:
                with self.subTest(target=target.name, token=token):
                    self.assertNotIn(token, text)
