"""Use the application MIME setup, not a browser-harness workaround."""
import mimetypes

from django.apps import apps
from django.contrib.staticfiles.views import serve
from django.test import RequestFactory, SimpleTestCase


class StaticModuleTests(SimpleTestCase):
    def test_windows_plain_text_mapping_is_corrected_for_module_responses(self):
        previous = mimetypes.guess_type("module.mjs")[0]
        try:
            mimetypes.add_type("text/plain", ".mjs")
            apps.get_app_config("report_v2").ready()
            for path in ("report_v2/page_state.mjs", "report_v2/widgets/boot.mjs"):
                with self.subTest(path=path):
                    response = serve(RequestFactory().get("/static/" + path), path, insecure=True)
                    try:
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response["Content-Type"], "text/javascript")
                    finally:
                        response.close()
        finally:
            if previous:
                mimetypes.add_type(previous, ".mjs")
