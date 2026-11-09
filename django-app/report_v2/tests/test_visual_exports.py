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

    def test_email_chart_image_replaces_all_data_tables(self):
        doc = self.document()
        doc["widgets"][0].update(type="bar", payload={"aggregates": {"n": 3},
            "series": [{"group": "Studies", "category": "A", "value": 3}]})
        vm = _email_view_model(doc, {"metric": "cid:metric@primer-llm"})
        self.assertEqual(vm["widgets"][0]["tables"], [])

    def test_email_matrix_and_grouped_values_keep_web_presentations(self):
        doc = {"widgets": [
            {"widget_id": "matrix", "title": "Matrix", "type": "confusion_matrix",
             "payload": {"classes": [0, 1], "cells": [[3, 1], [2, 4]],
                         "row_totals": [4, 6], "accuracy": {"value": .7}}},
            {"widget_id": "values", "title": "Accuracy", "type": "value", "measurement": "accuracy",
             "payload": {"units": {"accuracy": "rate[0,1]"}, "grouped_values": [
                 {"name": "Site A", "aggregates": {"accuracy": .85}, "ci": {"accuracy": {"available": True, "lower": .8, "upper": .9}}}]}}]}
        vm = _email_view_model(doc, {})
        html = render_to_string("report_v2/email.html", {"email": vm})
        self.assertIn("85.0%", html)
        self.assertIn("95% CI 80.0% to 90.0%", html)
        self.assertIn("Ground truth", html)
        self.assertIn("Prediction", html)
        self.assertIn("background-color: rgb(", html)
        self.assertNotIn("Measured values", html)

    def test_email_keeps_calendar_periods_for_values_and_heatmaps(self):
        doc = self.document()
        widget = doc["widgets"][0]
        result = widget["payload"]
        widget["payload"] = {"time_groups": [{"label": "2026-01-01", "payload": result}]}
        doc["widgets"].append({"widget_id": "matrix", "type": "confusion_matrix", "payload": {
            "time_groups": [{"label": "2026-01-01", "payload": {"classes": [0, 1],
                            "cells": [[3, 1], [2, 4]], "accuracy": {"value": .7}}}]}})
        html = render_to_string("report_v2/email.html", {"email": _email_view_model(doc, {})})
        self.assertIn("01/01/2026", html)
        self.assertIn("85.0%", html)
        self.assertIn("70.0%", html)
        self.assertIn("background-color: rgb(", html)

    def test_email_summary_table_uses_web_rows_instead_of_raw_aggregates(self):
        doc = {"widgets": [{"widget_id": "summary", "type": "table", "measurement": "classification_summary",
               "payload": {"aggregates": {"summary": {"denominator": 100}},
                           "units": {"accuracy": "rate[0,1]", "n": "count"},
                           "rows": [{"site": "Site A", "accuracy": .85, "n": 100}]}}]}
        vm = _email_view_model(doc, {})
        html = render_to_string("report_v2/email.html", {"email": vm})
        self.assertIn("85.0%", html)
        self.assertIn("Site A", html)
        self.assertNotIn("denominator", html)
        self.assertEqual(vm["widgets"][0]["rows_note"], "")
        self.assertEqual(vm["widgets"][0]["tables"][0]["kind"], "summary")
