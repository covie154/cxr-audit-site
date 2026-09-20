"""Task 16: render all packaged seed widgets with synthetic evaluated payloads."""
import json
import unittest
from urllib.parse import urlparse

from django.test import SimpleTestCase

from report_v2 import views
from report_v2.definitions.loader import load_report_definition
from report_v2.seed import report_seed_text
from . import test_browser_gallery15 as gallery
from . import test_seed as seed_tests


@unittest.skipUnless(gallery._PW_LAUNCH_OK, "Playwright Chromium unavailable")
class SeedBrowserTests(SimpleTestCase):
    def test_all_seventeen_evaluated_seed_widgets_render(self):
        doc = load_report_definition(report_seed_text())
        widgets = []
        for widget in views._layout_widgets(doc).values():
            rows = seed_tests.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)
            payload = views._evaluate(doc, widget, rows=rows)
            widgets.append({"id": widget["id"], "type": widget["type"], "payload": payload})
        html = """<!doctype html><html><head><style>
        .widget-frame { width:800px; min-height:250px; }
        </style><script src='/vendor/echarts.min.js'></script></head><body>
        <script type='module'>
        import {registry} from '/widgets/registry.mjs';
        await import('/widgets/boot.mjs');
        window.seedErrors = [];
        const widgets = SEED_JSON;
        for (const widget of widgets) {
            const node = document.createElement('section');
            node.className = 'widget-frame';
            node.dataset.widgetId = widget.id;
            const body = document.createElement('div');
            body.className = 'widget-body';
            node.append(body);
            document.body.append(node);
            try { registry.render(widget.type, body, widget.payload, {}); }
            catch (error) { window.seedErrors.push(widget.id + ': ' + error.message); }
        }
        window.seedReady = true;
        </script></body></html>""".replace("SEED_JSON", json.dumps(widgets, default=str).replace("<", "\\u003c"))
        with gallery.sync_playwright() as pw, pw.chromium.launch(headless=True) as browser:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def serve(route):
                path = urlparse(route.request.url).path
                if path == "/index.html":
                    route.fulfill(body=html, content_type="text/html")
                elif path == "/vendor/echarts.min.js":
                    route.fulfill(body=gallery.VENDOR.read_text(encoding="utf-8", errors="replace"),
                                  content_type="text/javascript")
                elif path.startswith("/widgets/") and path.rsplit("/", 1)[-1] in gallery.WIDGET_FILES:
                    route.fulfill(body=(gallery.WIDGETS_DIR / path.rsplit("/", 1)[-1]).read_text(encoding="utf-8"),
                                  content_type="text/javascript")
                else:
                    route.fulfill(status=404, body="")

            page.route("**/*", serve)
            page.goto("http://rv2seed.test/index.html")
            page.wait_for_function("window.seedReady === true")
            self.assertEqual(page.evaluate("window.seedErrors"), [])
            self.assertEqual(errors, [])
            self.assertEqual(page.locator(".widget-frame").count(), 17)
            for widget in widgets:
                self.assertTrue(page.locator('[data-widget-id="' + widget["id"] + '"]').inner_text().strip())
            self.assertGreaterEqual(page.locator("canvas").count(), 5)
