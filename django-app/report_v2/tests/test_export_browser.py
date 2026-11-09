"""Synthetic Report V2 print/email journey in real Chromium; no deployment data or SMTP."""
import tempfile
import time
import unittest
from pathlib import Path

from report_v2.tests.test_browser_layout import _Server, _PW_LAUNCH_OK, sync_playwright


@unittest.skipUnless(_PW_LAUNCH_OK, "playwright/chromium unavailable")
class BrowserExportTests(unittest.TestCase):
    def test_loaded_report_opens_charts_in_new_tab_and_captures_email(self):
        with tempfile.TemporaryDirectory(prefix="rv2-exports-") as scratch:
            server = _Server(Path(scratch))
            try:
                server.migrate()
                server.create_users()
                server.seed_rows(2000)
                done = server._manage_shell(
                    "from pathlib import Path\n"
                    "from report_v2.definitions.repository import DefinitionRepository\n"
                    "from django.conf import settings\n"
                    "from upload.models import CXRStudy\n"
                    "from django.db.models import F\n"
                    "CXRStudy.objects.update(gt_llm=F('gt_manual'), time_to_clinical_decision_seconds=1800, calcification=0, cardiomegaly=0, fibrosis=0, mediastinal_widening=0, nodule=0, pleural_effusion=0, pneumoperitoneum=0, pneumothorax=0)\n"
                    "text=Path('report_v2/seed/showcase.v1.yaml').read_text(encoding='utf-8').replace('height: 1','height: 5')\n"
                    "DefinitionRepository(settings.REPORT_V2_ROOT, project_id='prime').publish('showcase', text)\n"
                )
                self.assertEqual(done.returncode, 0, done.stdout)
                server.start()
                jar, _ = server.login("browser-admin", "pw-strong-1")
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    try:
                        context = browser.new_context(viewport={"width": 1440, "height": 1000})
                        context.add_cookies([{"name": "sessionid", "value": server.session_cookie(jar), "url": server.base}])
                        page = context.new_page()
                        errors = []
                        context.on("page", lambda tab: tab.on("pageerror", lambda exc: errors.append(str(exc))))
                        page.on("pageerror", lambda exc: errors.append(str(exc)))
                        report_url = server.base + "/report/showcase/"
                        page.goto(report_url, wait_until="networkidle")
                        page.wait_for_function("Array.from(document.querySelectorAll('.widget-frame:not([data-decoration])')).every(x => x.getAttribute('aria-busy') === 'false')")
                        expected_charts = page.locator("canvas").count()
                        self.assertEqual(expected_charts, 4, page.locator(".widget-error, .widget-summary").all_text_contents())
                        started = time.monotonic()
                        with page.expect_popup() as opened:
                            page.locator('[data-action="print"]').click()
                        printed = opened.value
                        printed.wait_for_url("**/print/**")
                        printed.wait_for_function("document.documentElement.dataset.printReady === 'true'")
                        print("Loaded-report export ready in", round(time.monotonic() - started, 2), "seconds (2,000 synthetic studies)")
                        self.assertEqual(page.url, report_url)
                        self.assertEqual(printed.locator("canvas").count(), expected_charts)
                        printed.wait_for_function("Array.from(document.querySelectorAll('canvas')).every(x => x.clientHeight > 120 && x.clientWidth < innerWidth)")
                        self.assertTrue(printed.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), printed.evaluate("Array.from(document.querySelectorAll('*')).filter(x=>x.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(x=>({tag:x.tagName,cls:x.className,width:x.getBoundingClientRect().width,right:x.getBoundingClientRect().right}))"))
                        self.assertEqual(printed.locator('[data-export-fallback]:visible').count(), 0)
                        self.assertTrue(printed.locator('[data-type="confusion_matrix"] .widget-confusion').is_visible())
                        self.assertTrue(printed.locator('[data-print-button]').is_enabled())
                        printed.emulate_media(media="print")
                        self.assertTrue(printed.locator('[data-type="confusion_matrix"] .widget-confusion').is_visible())
                        self.assertEqual(printed.locator('[data-export-fallback]:visible').count(), 0)
                        printed.wait_for_function("Array.from(document.querySelectorAll('canvas')).every(x => x.clientHeight > 120 && x.clientWidth < innerWidth)")
                        # Capture the actual outbound body, then let the isolated locmem backend send it.
                        with page.expect_request("**/email/") as sending:
                            page.locator('[data-action="email"]').click()
                            page.locator('[data-role="email-recipients"]').fill("synthetic@example.invalid")
                            page.locator('[data-action="email-send"]').click()
                        body = sending.value.post_data_json
                        self.assertEqual(len(body["images"]), expected_charts)
                        self.assertTrue(all(value.startswith("data:image/png;base64,") for value in body["images"].values()))
                        page.get_by_text("Sent to synthetic@example.invalid.", exact=True).wait_for()
                        self.assertEqual(errors, [])
                        # Keep small synthetic visual evidence outside the repository.
                        evidence = Path(tempfile.gettempdir()) / "primer-export-evidence"
                        evidence.mkdir(exist_ok=True)
                        printed.emulate_media(media="screen")
                        printed.wait_for_function("document.documentElement.scrollWidth <= innerWidth + 1 && Array.from(document.querySelectorAll('canvas')).every(x => x.clientHeight > 120)")
                        printed.screenshot(path=str(evidence / "showcase-print.png"), full_page=True)
                        print("Synthetic export screenshot:", evidence / "showcase-print.png")
                        from django.template.loader import render_to_string
                        from report_v2.exports import _email_view_model
                        document = printed.evaluate("""() => ({widgets: Array.from(document.querySelectorAll('[data-print-widget]')).map(card => ({
                            widget_id:card.dataset.printWidget, title:card.querySelector('h2').textContent,
                            type:card.dataset.type, measurement:card.dataset.measurement,
                            layout:{width:parseInt(card.style.gridColumn.match(/[0-9]+/)[0])},
                            payload:JSON.parse(card.querySelector('script[type="application/json"]').textContent)
                        }))})""")
                        document.update(title="Synthetic Showcase", slug="showcase", version="showcase@r1", project_id="prime", generated="2026-11-09 (synthetic)")
                        vm = _email_view_model(document, body["images"])
                        email_page = context.new_page()
                        email_page.set_content(render_to_string("report_v2/email.html", {"email": vm}))
                        email_page.wait_for_function("Array.from(document.images).every(x => x.complete && x.naturalWidth > 0)")
                        self.assertEqual(email_page.locator('img').count(), expected_charts)
                        self.assertNotIn('denominator=', email_page.locator('body').inner_text())
                        self.assertLess(email_page.locator('table[role="presentation"]').first.locator('td').first.bounding_box()["width"], 400)
                        self.assertTrue(email_page.get_by_text('Prediction', exact=True).is_visible())
                        email_page.screenshot(path=str(evidence / "showcase-email.png"), full_page=True)
                    finally:
                        browser.close()
            finally:
                server.stop()
