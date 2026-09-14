# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 14A browser/layout suite: structural stabilisation + registry renderers under real Chromium.

The suite boots ONE throwaway dev server (report_v2.tests.browser_settings, a tmp SQLite, a tmp
REPORT_V2_ROOT) over loopback, publishes a synthetic four-widget layout, seeds the study table with
SYNTHETIC rows only (never clinical, never the production ``db/`` tree), then drives it with Playwright
Chromium. Every class is skipped cleanly when Playwright / Chromium tooling is unavailable; when the
tooling is present the assertions must pass. Screenshots land in ``/tmp/rv2-14a-evidence`` for review.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import socket
import time
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Playwright import + probe (byte-for-byte import line, guarded).
try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except Exception:  # pragma: no cover - tooling absent in some environments
    sync_playwright = None
    HAVE_PW = False

_PW_LAUNCH_OK = False
if HAVE_PW:
    try:
        with sync_playwright() as _probe:
            _probe_browser = _probe.chromium.launch(headless=True)
            _probe_browser.close()
        _PW_LAUNCH_OK = True
    except Exception:  # pragma: no cover
        _PW_LAUNCH_OK = False

HERE = Path(__file__).resolve().parent
DJANGO_APP = HERE.parent.parent                       # .../django-app
EVIDENCE = Path("/tmp/rv2-14a-evidence")

DEF_ID = "browser14a"

# A synthetic, non-clinical four-widget layout (value width 3, table width 12, line + bar width 6).
# Every widget measures ``record_count`` over D-30..D with the date/site/compare-by controls.
LAYOUT = """\
schema_version: 1
project: prime
id: browser14a
title: Browser Layout 14A
grid:
  columns: 12
  row_height_px: 64
sections:
- id: s1
  title: Widgets
  widgets:
  - id: bv
    title: Value Widget
    type: value
    layout:
      width: 3
      height: 2
    query:
      measurement: record_count
      inputs: {}
    window:
      start: 'D-30'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
  - id: bt
    title: Table Widget
    type: table
    layout:
      width: 12
      height: 6
    query:
      measurement: record_count
      inputs: {}
    window:
      start: 'D-30'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
  - id: bl
    title: Line Widget
    type: line
    layout:
      width: 6
      height: 4
    query:
      measurement: record_count
      inputs: {}
    window:
      start: 'D-30'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
  - id: br
    title: Bar Widget
    type: bar
    layout:
      width: 6
      height: 4
    query:
      measurement: record_count
      inputs: {}
    window:
      start: 'D-30'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: [site]
    ci:
      enabled: false
    export: full
"""

_SEED_ONE_LINER = (
    "from datetime import datetime, timedelta\n"
    "from upload.models import CXRStudy\n"
    "N = int(__import__('os').environ.get('SEED_ROWS', '40'))\n"
    "now = datetime.now()\n"
    "CXRStudy.objects.all().delete()\n"
    "CXRStudy.objects.bulk_create([\n"
    "    CXRStudy(accession_no=9300000+k, workplace=('SYNTH-SITE-A' if k % 2 else 'SYNTH-SITE-B'),\n"
    "             procedure_start_date=now - timedelta(days=(k % 24) + 1), gt_manual=(k % 2),\n"
    "             atelectasis=float(k % 100), consolidation=float((k * 7) % 100))\n"
    "    for k in range(N)\n"
    "])\n"
    "print('ROWS', CXRStudy.objects.count())\n"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _intersects(a, b, *, tol: float = 0.5) -> bool:
    """True when two {x,y,width,height} rects overlap by more than a hair (touching edges are ok)."""
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    if ax2 <= b["x"] + tol or bx2 <= a["x"] + tol:
        return False
    if ay2 <= b["y"] + tol or by2 <= a["y"] + tol:
        return False
    return True


class _Server:
    """A single throwaway runserver with a migrated tmp database and a synthetic seed."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.root = tmp / "definitions"
        self.env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "report_v2.tests.browser_settings",
            "DATABASE_NAME": str(tmp / "browser.sqlite3"),
            "AUDIT_DATABASE_NAME": str(tmp / "audit.sqlite3"),
            "REPORT_V2_ROOT": str(self.root),
            "PYTHONUNBUFFERED": "1",
            "SEED_ROWS": os.environ.get("SEED_ROWS", "40"),
        }
        self.proc = None

    def _manage(self, *args: str, command: str | None = None) -> subprocess.completedprocess:
        argv = [sys.executable, "manage.py", *args]
        return subprocess.run(argv, cwd=str(DJANGO_APP), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def _manage_shell(self, liner: str) -> subprocess.completedprocess:
        return subprocess.run([sys.executable, "manage.py", "shell", "--command", liner],
                             cwd=str(DJANGO_APP), env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def migrate(self) -> None:
        done = self._manage("migrate", "--noinput")
        assert done.returncode == 0, f"migrate failed:\n{done.stdout}\n{done.stderr}"

    def create_users(self) -> None:
        liner = (
            "from django.contrib.auth.models import User\n"
            "User.objects.filter(username='browser-admin').exists() or User.objects.create_superuser("
            "username='browser-admin', email='browser-admin@example.invalid', password='pw-strong-1')\n"
            "User.objects.filter(username='browser-normal').exists() or User.objects.create_user("
            "username='browser-normal', email='browser-normal@example.invalid', password='pw-strong-1')\n"
            "print('USERS', User.objects.count())\n"
        )
        done = self._manage_shell(liner)
        assert done.returncode == 0, f"user seed failed:\n{done.stdout}\n{done.stderr}"

    def seed_rows(self, n: int) -> None:
        self.env["SEED_ROWS"] = str(n)
        done = self._manage_shell(_SEED_ONE_LINER)
        assert done.returncode == 0, f"row seed failed:\n{done.stdout}\n{done.stderr}"

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{self.port}",
             "--noreload", "--insecure"],
            cwd=str(DJANGO_APP), env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self._wait_ready()

    def _wait_ready(self, *, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        last: object = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:                     # the server died on boot
                break
            try:
                with urllib.request.urlopen(f"{self.base}/login/", timeout=2) as response:
                    if getattr(response, "status", response.code) == 200:
                        return
            except Exception as exc:                              # not up yet, keep polling
                last = exc
            time.sleep(0.3)
        raise AssertionError(f"dev server did not become ready on {self.base} (last={last!r})")

    def _open(self):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPDefaultErrorHandler(),
        )
        return jar, opener

    def get(self, path: str, *, jar=None, opener=None):
        if opener is None:
            jar, opener = self._open()
        request = urllib.request.Request(self.base + path, method="GET")
        try:
            response = opener.open(request)
            body = response.read().decode("utf-8", "replace")
            return getattr(response, "status", response.code), body, jar
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), jar

    def _csrf_from_cookie(self, jar) -> str:
        for cookie in jar:
            if cookie.name == "csrftoken":
                return cookie.value
        return ""

    def login(self, username: str, password: str):
        """Log in over plain http with a cookie jar; return (jar, opener).

        Success is judged by the sessionid cookie the server sets on the post-login redirect, not the
        (already-redirect-followed, hence always 2xx) final status."""
        jar, opener = self._open()
        self.get("/login/", jar=jar, opener=opener)             # prime the csrftoken cookie
        token = self._csrf_from_cookie(jar)
        data = urllib.parse.urlencode(
            {"csrfmiddlewaretoken": token, "username": username, "password": password}
        ).encode()
        request = urllib.request.Request(self.base + "/login/", data=data, method="POST")
        try:
            opener.open(request).read()
        except urllib.error.HTTPError:
            pass
        return jar, opener

    def publish(self, jar, opener) -> dict:
        token = self._csrf_from_cookie(jar)
        data = urllib.parse.urlencode(
            {"csrfmiddlewaretoken": token, "def_id": DEF_ID, "yaml_text": LAYOUT}
        ).encode()
        request = urllib.request.Request(
            self.base + "/report/layout/editor/publish/", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
        )
        response = opener.open(request)
        body = response.read().decode("utf-8", "replace")
        return json.loads(body)

    def session_cookie(self, jar) -> str:
        for cookie in jar:
            if cookie.name == "sessionid":
                return cookie.value
        return ""

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


@unittest.skipUnless(HAVE_PW and _PW_LAUNCH_OK, "playwright/chromium unavailable")
class BrowserLayoutTests(unittest.TestCase):
    """One shared browser + server across the width/registry/editor checks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="rv2-14a-browser-"))
        cls.server = _Server(cls.tmp)
        cls.server.migrate()
        cls.server.create_users()
        cls.server.seed_rows(40)
        cls.server.start()
        jar, opener = cls.server.login("browser-admin", "pw-strong-1")
        cls.admin_session = cls.server.session_cookie(jar)
        if not cls.admin_session:
            raise AssertionError("admin login did not establish a session cookie")
        cls.server.publish(jar, opener)
        cls.report_url = f"{cls.server.base}/report/{DEF_ID}/"

        cls.pw = sync_playwright()
        cls.pw = cls.pw.start()                     # start() returns the live Playwright instance
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.context = cls.browser.new_context(viewport={"width": 1440, "height": 900})
        cls.context.add_cookies([{
            "name": "sessionid", "value": cls.admin_session,
            "url": cls.server.base,
        }])
        cls.page = cls.context.new_page()
        EVIDENCE.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        for attr in ("page", "context", "browser"):
            obj = getattr(cls, attr, None)
            try:
                if attr == "browser":
                    obj.close()
                else:
                    obj.close() if obj is not None else None
            except Exception:
                pass
        try:
            cls.pw.stop()
        except Exception:
            pass
        if getattr(cls, "server", None) is not None:
            cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ------------------------------------------------------------------ #
    def _goto(self, url: str, *, width: int, height: int) -> None:
        self.page.set_viewport_size({"width": width, "height": height})
        self.page.goto(url, wait_until="networkidle")
        self.page.wait_for_timeout(250)

    def _rects(self, selector: str) -> list[dict]:
        return self.page.evaluate(
            "() => Array.from(document.querySelectorAll(%r)).map((n) => { const r = n.getBoundingClientRect(); "
            "return {x: r.left, y: r.top, width: r.right - r.left, height: r.bottom - r.top}; })" % selector
        )

    def _assert_no_frame_overlap(self) -> None:
        rects = self._rects(".report-grid > .widget-frame")
        self.assertTrue(len(rects) >= 4, "expected four widget frames")
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                self.assertFalse(
                    _intersects(rects[i], rects[j]),
                    f"frames {i} and {j} overlap: {rects[i]} vs {rects[j]}",
                )

    def _assert_within_frame(self, frame_index: int) -> None:
        frames = self.page.locator(".report-grid > .widget-frame")
        frame = frames.nth(frame_index)
        fr = frame.bounding_box()
        for sel in ("input", "select", "button"):
            for control in frame.locator(f".widget-controls {sel}").element_handles():
                self.assertTrue(control.is_visible(), f"control {sel} not visible")
                box = control.bounding_box()
                self.assertGreaterEqual(box["x"], fr["x"] - 1, "control left outside frame")
                self.assertLessEqual(box["x"] + box["width"], fr["x"] + fr["width"] + 1, "control right outside frame")

    def _assert_inner_regions_no_overlap(self) -> None:
        for index in range(self.page.locator(".report-grid > .widget-frame").count()):
            frame = self.page.locator(".report-grid > .widget-frame").nth(index)
            regions = {}
            for cls_name in ("widget-controls", "widget-summary", "widget-body"):
                node = frame.locator(f".{cls_name}").first
                if node.count():
                    regions[cls_name] = node.bounding_box()
            keys = list(regions)
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    self.assertFalse(
                        _intersects(regions[keys[i]], regions[keys[j]]),
                        f"frame {index}: {keys[i]} overlaps {keys[j]}",
                    )

    # -- 1. no page overflow / overlap at all widths + keyboard reachability ---------------- #
    def test_no_page_overflow_or_overlap_at_all_widths(self):
        for width, height in ((1440, 900), (1024, 768), (390, 844)):
            with self.subTest(width=width, height=height):
                self._goto(self.report_url, width=width, height=height)
                metrics = self.page.evaluate(
                    "() => { const d = document.documentElement; "
                    "return {sw: d.scrollWidth, cw: d.clientWidth, bsw: document.body.scrollWidth, bcw: document.body.clientWidth}; }"
                )
                self.assertLessEqual(metrics["sw"], metrics["cw"] + 1, "horizontal page overflow")
                self.assertLessEqual(metrics["bsw"], metrics["bcw"] + 1, "horizontal body overflow")
                self._assert_no_frame_overlap()
                self._assert_inner_regions_no_overlap()
                for index in range(self.page.locator(".report-grid > .widget-frame").count()):
                    self._assert_within_frame(index)
                self._assert_keyboard_reaches_an_apply()
                self._shot(f"page-{DEF_ID}-{width}.png", full_page=True)

    def _assert_keyboard_reaches_an_apply(self) -> None:
        self.page.evaluate("() => { document.body.focus(); }")
        for _ in range(60):
            self.page.keyboard.press("Tab")
            state = self.page.evaluate(
                "() => { const a = document.activeElement; if (!a) { return null; } "
                "return {action: a.getAttribute('data-action'), inFrame: !!(a.closest && a.closest('.widget-frame'))}; }"
            )
            if state and state.get("action") == "apply" and state.get("inFrame"):
                return
        self.fail("no Apply button reachable via Tab within 60 presses")

    # -- 2. a long table grows without clipping and re-renders cleanly ----------------------- #
    def test_table_grows_without_clipping(self):
        self.server.seed_rows(120)
        try:
            self._goto(self.report_url, width=1440, height=900)
            frame = self.page.locator('.widget-frame[data-widget-id="bt"]')
            body = frame.locator(".widget-body").first
            self.assertGreaterEqual(body.evaluate("(n) => n.scrollHeight"), 1)
            section_bottom = self.page.locator(".report-section").first.bounding_box()
            frame_box = frame.bounding_box()
            self.assertLessEqual(
                frame_box["y"] + frame_box["height"],
                section_bottom["y"] + section_bottom["height"] + 2,
                "the table frame must not grow past its section bottom",
            )
            with self.page.expect_response(
                lambda r: f"/widget/bt/data/" in r.url and r.status == 200, timeout=15000
            ):
                frame.locator('[data-action="apply"]').first.click()
            self.page.wait_for_timeout(300)
            self.assertTrue(frame.locator(".widget-live").first.count() >= 1, "live region missing")
            more = frame.locator('[data-action="more"]').first
            self.assertTrue(more.is_visible(), "show-more button should be visible when truncated")
            self._assert_no_frame_overlap()
            self._shot(f"page-longtable-1440.png", full_page=True)
        finally:
            self.server.seed_rows(40)

    # -- 3. the registry renderers paint line + bar ------------------------------------------ #
    def test_registry_renderers_paint(self):
        self._goto(self.report_url, width=1440, height=900)
        booted = self.page.evaluate("() => !!(window.__rv2widgets && window.__rv2widgets.bootReady)")
        self.assertTrue(booted, "boot.mjs did not flag window.__rv2widgets.bootReady")
        for widget_id in ("bl", "br"):
            with self.subTest(widget=widget_id):
                frame = self.page.locator(f'.widget-frame[data-widget-id="{widget_id}"]')
                with self.page.expect_response(
                    lambda r: f"/widget/{widget_id}/data/" in r.url and r.status == 200, timeout=15000
                ):
                    frame.locator('[data-action="apply"]').first.click()
                self.page.wait_for_timeout(500)
                canvases = frame.locator("canvas").count()
                self.assertGreaterEqual(canvases, 1, "echarts must paint at least one canvas")
                self.assertGreaterEqual(frame.locator(".widget-a11y").count(), 1, "a11y table missing")
                body_text = frame.locator(".widget-live").first.inner_text()
                for forbidden in ("<", "undefined", "NaN"):
                    self.assertNotIn(forbidden, body_text)

    # -- 4. the admin page links to the report-specific editor ------------------------------- #
    def test_editor_navigation_from_admin_page(self):
        self._goto(self.report_url, width=1440, height=900)
        link = self.page.locator('[data-role="edit-layout"]').first
        self.assertEqual(link.get_attribute("href"), f"/report/layout/editor/{DEF_ID}/")
        editor_url = self.server.base + link.get_attribute("href")
        link.click()
        self.page.wait_for_load_state("networkidle")
        self.assertTrue(self.page.url.endswith(f"/report/layout/editor/{DEF_ID}/"), self.page.url)
        selector_option = self.page.locator(f'select option[value="{DEF_ID}"]').first
        self.assertTrue(selector_option.count() >= 1)
        self.assertIsNotNone(selector_option.get_attribute("data-state"))
        textarea = self.page.locator("#id_yaml_text").first
        self.assertIn("Browser Layout 14A", textarea.input_value())
        self.assertFalse((self.server.root / "drafts" / DEF_ID).exists(), "the editor GET must not write a draft")
        self._shot(f"editor-1440.png", full_page=True)

        # An ordinary user gets no edit-layout affordance at all.
        jar, opener = self.server.login("browser-normal", "pw-strong-1")
        self.assertTrue(self.server.session_cookie(jar), "normal login must establish a session")
        ordinary_code, ordinary_body, _ = self.server.get(f"/report/{DEF_ID}/", jar=jar, opener=opener)
        self.assertEqual(ordinary_code, 200)
        self.assertNotIn('data-role="edit-layout"', ordinary_body)
        self.assertNotIn("Edit layout", ordinary_body)

    # -- 5. the legacy report route is untouched --------------------------------------------- #
    def test_legacy_report_untouched(self):
        # Reuse the admin session (a fresh login keeps the legacy redirect chain independent of the
        # browser's injected session).
        jar, opener = self.server.login("browser-admin", "pw-strong-1")
        legacy_code, _body, _ = self.server.get("/report-old/", jar=jar, opener=opener)
        self.assertLess(legacy_code, 500, "legacy report must not 5xx")

    # -- screenshot helper ------------------------------------------------------------------- #
    def _shot(self, name: str, *, full_page: bool = True) -> None:
        path = EVIDENCE / name
        self.page.screenshot(path=str(path), full_page=full_page)
        print(f"SCREENSHOT {path.resolve()}")
