from django.test import SimpleTestCase, override_settings
from django.template.loader import render_to_string
from report_v2.exports import _print_view_model, _email_view_model


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class VisualExportTests(SimpleTestCase):
    def document(self):
        return {"widgets": [{"widget_id": "metric", "title": "Accuracy", "type": "value",
            "measurement": "accuracy", "layout": {"width": 4, "height": 2},
            "applied": {"date": {"start": "D-7", "end": "D"}},
            "payload": {"aggregates": {"accuracy": .85}, "units": {"accuracy": "rate[0,1]"},
                "dates": {"window_start": "2026-01-01", "window_end": "2026-01-08"},
                "caption": "</script><script>alert(1)</script>"}}]}

    def test_print_reuses_safe_payload_and_frozen_geometry(self):
        vm = _print_view_model(self.document())
        self.assertEqual(vm["widgets"][0]["width"], 4)
        html = render_to_string("report_v2/print.html", {"print": vm})
        self.assertIn("report_v2/print.mjs", html)
        self.assertIn('grid-column:span 4', html)
        self.assertIn('data-measurement="accuracy"', html)
        self.assertIn('01/01/2026 .. 08/01/2026', html)
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('application/json', html)

    def test_email_formats_primary_value_and_preserves_window(self):
        vm = _email_view_model(self.document(), {})
        html = render_to_string("report_v2/email.html", {"email": vm})
        self.assertIn('85.0%', html)
        self.assertIn('01/01/2026 .. 08/01/2026', html)
