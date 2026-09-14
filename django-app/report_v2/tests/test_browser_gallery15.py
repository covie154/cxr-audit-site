# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Task 15B synthetic gallery browser suite: the seven registry renderers painted under real Chromium.

Boots NO Django and spawns NO subprocess: a single Playwright route handler serves one synthetic HTML
document (built from the shared fixtures sidecar), the shipped widget ES modules off disk (whitelisted
leaf names only) and the vendored ECharts off disk. Every fixture is SYNTHETIC (task-15 canonical
literals) so no clinical value ever reaches the page. The suite asserts the boot flag, the eight
sections, real canvas painting via the vendored ECharts (pinned per canvas by a nonzero layout-box assertion), the percent/count confusion tables, the boxplot
alternative table, the absence of undefined/NaN text, and that the share/confusion widgets carry no
benchmark/mark styling. Screenshots land in ``/tmp/rv2-15-evidence``. Cleanly skipped when the
Playwright/Chromium tooling is unavailable; when present the assertions must pass.
"""
from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path

# Playwright import + probe (byte-for-byte import line, guarded) — mirrors test_browser_layout.py.
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
WIDGETS_DIR = DJANGO_APP / "report_v2" / "static" / "report_v2" / "widgets"
GALLERY_DIR = HERE / "js" / "gallery"
VENDOR = DJANGO_APP / "report_v2" / "static" / "report_v2" / "vendor" / "echarts.min.js"
EVIDENCE = Path("/tmp/rv2-15-evidence")

BASE_URL = "http://rv2gallery.test"

WIDGET_FILES = [
    "registry.mjs", "boot.mjs", "format.mjs", "value.mjs", "table.mjs",
    "line.mjs", "bar.mjs", "pie.mjs", "confusion.mjs", "boxplot.mjs",
]

REQUIRED_KINDS = ["value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"]

# The node --dump sidecar is the single source of truth the browser shares with the node suites.
_SIDEcar = GALLERY_DIR / "fixtures.task15.json"
if not _SIDEcar.exists():
    raise AssertionError(
        "task-15 fixtures sidecar missing at " + str(_SIDEcar)
        + "; regenerate it with: node report_v2/tests/js/gallery/synthetic_gallery.mjs --dump"
        " > report_v2/tests/js/gallery/fixtures.task15.json"
    )
FIXTURES_JSON = _SIDEcar.read_text(encoding="utf-8").strip()
FIXTURES = json.loads(FIXTURES_JSON)
assert len(FIXTURES) >= 8, "task-15 sidecar must carry at least eight fixtures"
assert set(item.get("kind") for item in FIXTURES) >= set(REQUIRED_KINDS), \
    "task-15 sidecar must cover all seven widget kinds"


def _build_gallery_html(base_url, echarts_source, fixtures_json):
    """Mirror synthetic_gallery.mjs buildGalleryHtml exactly, with python string concatenation."""
    lt = "<"
    script_open = lt + "script"
    script_close = "</scr" + "ipt>"
    script_json = lt + "script id=\"rv2-fixtures\" type=\"application/json\">"
    script_module = lt + "script type=\"module\">"
    html = "<!doctype html>"
    html += lt + "html>"
    html += lt + "head>"
    html += lt + "meta charset=\"utf-8\">"
    html += lt + "title>report_v2 synthetic gallery (task 15)</title>"
    html += script_open + ">" + echarts_source + script_close
    html += (
        lt + "style>body{font-family:sans-serif}.widget-frame{border:1px solid #ccc;"
        "margin:8px;padding:8px;width:640px;min-height:260px}.widget-chart,.widget-chart-box{width:100%;min-height:240px}</style>"
    )
    html += lt + "/head>"
    html += lt + "body>"
    html += lt + "h1>report_v2 synthetic gallery - task 15</h1>"
    for item in FIXTURES:
        kind = item["kind"]
        html += lt + "section class=\"gallery-item\" data-kind=\"" + kind + "\">"
        html += lt + "h2>" + kind + "</h2>"
        html += lt + "div class=\"widget-frame\" data-kind=\"" + kind + "\"></div>"
        html += lt + "/section>"
    html += script_json + fixtures_json + script_close
    html += script_module
    html += "import { registry } from \"" + base_url + "/widgets/registry.mjs\";\n"
    html += "await import(\"" + base_url + "/widgets/boot.mjs\");\n"
    html += "const fixtures = JSON.parse(document.getElementById(\"rv2-fixtures\").textContent);\n"
    html += "for (const fixture of fixtures) {\n"
    html += "  const node = document.querySelector('[data-kind=\"' + fixture.kind + '\"] .widget-frame');\n"
    html += "  registry.render(fixture.kind, node, fixture.payload, fixture.options);\n"
    html += "}\n"
    html += "window.__rv2gallery = { rendered: true };\n"
    html += script_close
    html += lt + "/body>"
    html += lt + "/html>"
    return html


@unittest.skipUnless(HAVE_PW and _PW_LAUNCH_OK, "playwright/chromium unavailable")
class BrowserGalleryTests(unittest.TestCase):
    """One shared headless Chromium + routed document across the gallery checks."""

    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        echarts_source = VENDOR.read_text(encoding="utf-8", errors="replace")
        cls.html = _build_gallery_html(BASE_URL, echarts_source, FIXTURES_JSON)
        cls.pw = sync_playwright()
        cls.pw = cls.pw.start()                     # start() returns the live Playwright instance
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.context = cls.browser.new_context(viewport={"width": 1440, "height": 1200})
        cls.page = cls.context.new_page()

        def _catch_all(route):
            route.fulfill(status=204, content_type="text/plain; charset=utf-8", body="")

        def _index(route):
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=cls.html)

        def _widget(route):
            leaf = request_leaf(route.request.url)
            if leaf not in WIDGET_FILES:
                route.fulfill(status=404, content_type="text/plain; charset=utf-8", body="unknown widget")
                return
            body = (WIDGETS_DIR / leaf).read_text(encoding="utf-8")
            route.fulfill(status=200, content_type="text/javascript", body=body)

        def _vendor(route):
            route.fulfill(status=200, content_type="text/javascript", body=echarts_source)

        # Catch-all FIRST, specifics LAST so Playwright's most-recent-first matching serves the specifics.
        cls.page.route("**/*", _catch_all)
        cls.page.route("**/index.html", _index)
        cls.page.route("**/widgets/*", _widget)
        cls.page.route("**/vendor/echarts.min.js", _vendor)

        cls.page.goto(BASE_URL + "/index.html", wait_until="networkidle")
        cls.page.wait_for_function(
            "() => window.__rv2gallery && window.__rv2gallery.rendered === true", timeout=15000
        )
        cls.page.wait_for_timeout(300)

    @classmethod
    def tearDownClass(cls):
        for attr in ("page", "context", "browser"):
            obj = getattr(cls, attr, None)
            try:
                if obj is not None:
                    obj.close()
            except Exception:  # pragma: no cover
                pass
        try:
            if getattr(cls, "pw", None) is not None:
                cls.pw.stop()
        except Exception:  # pragma: no cover
            pass

    # -- tests ----------------------------------------------------------------------------- #
    def test_a_boot_ready(self):
        booted = self.page.evaluate(
            "() => !!(window.__rv2widgets && window.__rv2widgets.bootReady === true)"
        )
        self.assertTrue(booted, "boot.mjs must flag window.__rv2widgets.bootReady")

    def test_b_eight_sections_and_all_kinds(self):
        self.assertEqual(self.page.locator(".gallery-item").count(), 8)
        for kind in REQUIRED_KINDS:
            expected = 2 if kind == "confusion_matrix" else 1
            self.assertEqual(
                self.page.locator('.gallery-item[data-kind="' + kind + '"]').count(),
                expected,
                "section count for " + kind,
            )

    def test_c_real_charts_paint_canvases(self):
        # "Real charts paint canvases" is pinned per canvas: every <canvas> must own a nonzero layout box on
        # BOTH axes (w>0 and h>0). A zero-height box proves echarts initialised into an unsized container and
        # painted nothing, even though the canvas elements themselves exist and are counted below.
        self.assertGreaterEqual(self.page.locator("canvas").count(), 4)
        boxes = self.page.evaluate(
            "() => Array.from(document.querySelectorAll('canvas')).map((c) => {"
            " const r = c.getBoundingClientRect();"
            " return { w: r.width, h: r.height };"
            " })"
        )
        self.assertGreaterEqual(len(boxes), 4)
        zero = [b for b in boxes if b["w"] <= 0 or b["h"] <= 0]
        self.assertEqual(zero, [], "every canvas must have a real painted layout box (w>0 and h>0); zero-sized: " + str(zero))

    def test_d_confusion_percent_section(self):
        # The percent confusion section is the first confusion_matrix section in DOM order (the sidecar
        # lists binary-percent at index 5 ahead of multiclass-count at index 6); target it explicitly so
        # the percent cell formatting and accuracy line are the ones asserted regardless of ordering.
        text = self.page.locator('.gallery-item[data-kind="confusion_matrix"]').nth(0).inner_text()
        for token in ("60.0%", "40.0%", "Accuracy: 62.5%"):
            self.assertIn(token, text)
        # Complement: the multiclass count section (nth 1) renders raw counts, not normalised shares.
        count_text = self.page.locator('.gallery-item[data-kind="confusion_matrix"]').nth(1).inner_text()
        self.assertIn("77.8%", count_text)
        self.assertNotIn("60.0%", count_text)

    def test_e_boxplot_alternative_table(self):
        section = self.page.locator('.gallery-item[data-kind="boxplot"]').first
        text = section.inner_text()
        self.assertIn("lower whisker", text)
        self.assertIn("upper whisker", text)
        self.assertIn("1 min 40 s", text)          # max/outlier duration cell (formatValue(100, 'seconds'))
        self.assertIn("1.5*IQR", text)             # alternative-table caption mentions the fence rule
        self.assertEqual(section.locator(".widget-a11y-row td:nth-child(7)").first.inner_text(), "6 s")
        self.assertEqual(section.locator(".widget-a11y-row td:nth-child(2)").first.inner_text(), "11")
        # NOTE: the benchmark markLine "5 minutes" label is drawn on the canvas, not the DOM, so it is
        # asserted at the option level in the node suite (widgets15 t13); the DOM side checks here are the
        # formatted quartile durations (median "6 s") and the count-as-n cell ("11"), not canvas glyphs.

    def test_f_no_undefined_or_nan_text(self):
        body = self.page.locator("body").first.inner_text()
        self.assertNotIn("undefined", body)
        self.assertNotIn("NaN", body)

    def test_g_share_and_confusion_carry_no_benchmark_styling(self):
        offenders = self.page.evaluate(
            "() => {"
            " const hits = [];"
            " for (const sel of ['[data-kind=\"pie\"]', '[data-kind=\"confusion_matrix\"]']) {"
            "   for (const root of document.querySelectorAll(sel)) {"
            "     for (const el of root.querySelectorAll('*')) {"
            "       const cs = (typeof el.className === 'string' ? el.className : '') || '';"
            "       const lc = cs.toLowerCase();"
            "       if (lc.includes('markline') || lc.includes('benchmark')) { hits.push(sel + '|' + cs); }"
            "     }"
            "   }"
            " }"
            " return hits;"
            "}"
        )
        self.assertEqual(offenders, [])

    def test_h_full_page_screenshot(self):
        self.page.screenshot(path=str(EVIDENCE / "gallery-1440.png"), full_page=True)
        self.assertTrue((EVIDENCE / "gallery-1440.png").exists())


def request_leaf(url):
    tail = url.split("?", 1)[0].split("#", 1)[0]
    return tail.rsplit("/", 1)[-1] if "/" in tail else tail


if __name__ == "__main__":
    unittest.main()
