"""Project-defined group controls and pooled summaries over synthetic rows only."""
from dataclasses import replace
from unittest import mock
from django.test import SimpleTestCase, override_settings
from report_v2 import views
from report_v2.definitions.loader import load_report_definition
from report_v2.projects.base import Dimension
from report_v2.projects.prime import get_project_definition
from report_v2.seed import report_seed_text
from report_v2.tests import test_seed


class GroupingTests(SimpleTestCase):
    def setUp(self):
        self.layout = load_report_definition(report_seed_text())
        self.widgets = views._layout_widgets(self.layout)

    def payload(self, widget_id, **kwargs):
        widget = self.widgets[widget_id]
        rows = kwargs.pop("rows", test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget))
        return views._evaluate(self.layout, widget, rows=rows, **kwargs)

    def test_every_card_declares_project_fields_and_controls(self):
        for widget in self.widgets.values():
            controls = views._allowed_controls(widget)
            self.assertTrue(controls["enabled"])
            self.assertEqual(controls["compare_by"], [{"id": "site", "label": "Site"}, {"id": "age", "label": "Age"}])
            payload = self.payload(widget["id"], comparison="age", grouping=["age"])
            self.assertIn("age", payload["group_options"])
            self.assertFalse(payload.get("error"))

    def test_age_boundaries_missing_and_invalid(self):
        dimension = get_project_definition().dimension("age")
        expected = ["<18", "<18", "18–39", "18–39", "40–59", "60–79", "80+", "Unknown", "Unknown", "Unknown"]
        values = [0, 17, 18, 39, 40, 60, 80, None, -1, float("nan")]
        self.assertEqual([dimension.group_value(value) for value in values], expected)
        with self.assertRaises(ValueError):
            Dimension("bad", "x", bands=(("a", 0, 20), ("b", 18, 40)))

    def test_overall_recomputed_over_selected_groups(self):
        prototype = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=self.widgets["site_metrics"])[0]
        rows = [dict(prototype, site="A", accession=100+i, gt_label=1, pred_label=1) for i in range(4)]
        rows.append(dict(prototype, site="B", accession=200, gt_label=1, pred_label=0))
        payload = self.payload("site_metrics", rows=rows)
        self.assertEqual(len(payload["rows"]), 3)
        self.assertEqual(payload["rows"][-1]["site"], "Overall")
        self.assertEqual(payload["rows"][-1]["accuracy"], .8)
        self.assertTrue(payload["overall_row"])
        selected = self.payload("site_metrics", rows=rows, filters={"site": ["B"]})
        self.assertEqual(selected["rows"][-1]["n"], 1)
        self.assertEqual(selected["rows"][-1]["accuracy"], 0)

    def test_none_and_empty_selection_are_explicit(self):
        widget = self.widgets["site_metrics"]
        _, _, comparison, grouping, _ = views._validate_overrides(widget, {"comparison": ""})
        payload = self.payload("site_metrics", comparison=comparison, grouping=grouping)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertFalse(payload["overall_row"])
        empty = self.payload("total", comparison="site", grouping=["site"], filters={"site": []})
        self.assertTrue(empty["empty"])
        self.assertEqual(empty["grouped_values"], [])

    def test_empty_group_selection_is_empty_on_every_card(self):
        for widget_id in self.widgets:
            with self.subTest(widget_id=widget_id):
                payload = self.payload(widget_id, comparison="site", grouping=["site"], filters={"site": []})
                self.assertTrue(payload["empty"])

    def test_grouped_values_and_age_selection(self):
        widget = self.widgets["total"]
        prototype = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)[0]
        rows = [dict(prototype, age=17, accession=1), dict(prototype, age=18, accession=2), dict(prototype, age=None, accession=3)]
        payload = self.payload("total", rows=rows, comparison="age", grouping=["age"], filters={"age": ["<18"]})
        self.assertEqual(len(payload["grouped_values"]), 1)
        self.assertEqual(payload["grouped_values"][0]["aggregates"]["n"], 1)
        self.assertEqual(payload["counts"]["matching"], 1)
        self.assertIn("Unknown", payload["group_options"]["age"])

    def test_group_labels_come_from_project_configuration(self):
        project = get_project_definition()
        alternate = replace(project, dimensions={**project.dimensions, "age": Dimension("age", "patient_age", label="Age band", bands=(("Young", 0, 40), ("Older", 40, None)))})
        with mock.patch("report_v2.views.get_project_definition", return_value=alternate):
            payload = self.payload("total", rows=[{"age": 45, "event_date": "2026-08-01"}], comparison="age", grouping=["age"])
            self.assertEqual(payload["group_options"]["age"], ["Young", "Older", "Unknown"])
            self.assertIn("Older", payload["grouped_values"][0]["name"])

    def test_unknown_group_field_and_nested_selection_rejected(self):
        with self.assertRaises(views.OverrideRejectedError):
            views._validate_overrides(self.widgets["total"], {"comparison": "patient_name"})
        with self.assertRaises(views.OverrideRejectedError):
            views._validate_overrides(self.widgets["total"], {"filters": {"age": [{"gt": 18}]}})

    def test_time_grouping_uses_calendar_buckets_on_every_card(self):
        widget = next(w for w in self.widgets.values() if w.get("bucket"))
        for size in ("day", "week", "month", "year"):
            views._validate_overrides(widget, {"time_grouping": size})
            payload = self.payload(widget["id"], time_grouping=size)
            self.assertFalse(payload.get("error"))
            self.assertTrue(payload["buckets"])
            self.assertTrue(all(b["size"] == size for b in payload["buckets"]))
        for widget_id in self.widgets:
            views._validate_overrides(self.widgets[widget_id], {"time_grouping": "day"})
        with self.assertRaises(views.OverrideRejectedError):
            views._validate_overrides(widget, {"time_grouping": "hour"})

    def test_relative_calendar_range_presets_are_valid(self):
        for token in ("D", "W", "M", "Y", "W-2", "M-3", "Y-1"):
            self.assertEqual(views._validate_date({"relative": token}), {"relative": token})

    def test_calendar_groups_keep_anchor_filters_and_export_values(self):
        from report_v2.exports import _widget_tables
        widget = self.widgets["total"]
        prototype = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)[0]
        rows = [dict(prototype, accession=1, event_date="2026-08-03", site="A"),
                dict(prototype, accession=2, event_date="2026-08-11", site="A"),
                dict(prototype, accession=3, event_date="2026-08-11", site="B")]
        payload = self.payload("total", rows=rows, time_grouping="week", filters={"site": ["A"]})
        self.assertEqual(len(payload["time_groups"]), 2)
        for group in payload["time_groups"]:
            self.assertEqual(group["payload"]["aggregates"]["n"], 1)
            self.assertEqual(group["payload"]["dates"]["anchor_date"], payload["dates"]["anchor_date"])
        tables = _widget_tables(payload)
        self.assertEqual(len(tables), 2)
        self.assertIn(payload["time_groups"][0]["label"], tables[0]["caption"])
        self.assertNotIn("time_groups", self.payload("total", rows=rows, time_grouping=""))

    def test_date_boundaries_are_validated_before_fetch(self):
        self.assertEqual(views._validate_date({"start": "W-2", "end": "M"}), {"start": "W-2", "end": "M"})
        for bad in ({"start": "2026-02-30", "end": "D"}, {"start": "W+2", "end": "D"},
                    {"start": "D", "end": "W--2"}, {"start": "D", "end": "D", "anchor": "2026-01-01"}):
            with self.assertRaises(views.OverrideRejectedError):
                views._validate_date(bad)

    @override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_yaml_boundaries_and_grouping_defaults_are_displayed_and_evaluated(self):
        from django.template.loader import render_to_string
        from report_v2.dates import InvalidOffsetError, resolve_window
        from datetime import date
        text = report_seed_text().replace("end: D", "end: W")
        layout = load_report_definition(text)
        widget = views._layout_widgets(layout)["total"]
        controls = views._allowed_controls(widget)
        frame = {"id": "total", "type": "value", "controls": controls}
        html = render_to_string("report_v2/page.html", {"sections_ctx": [{"widgets": [frame]}]})
        self.assertIn('data-date="start" value="12-12-2025"', html)
        self.assertIn('data-date="end" value="W"', html)
        self.assertIn('data-date-picker="start" value="2025-12-12"', html)
        self.assertIn('data-date-picker="end" value=""', html)
        self.assertIn('value="" selected>Overall', html)
        with self.assertRaises(InvalidOffsetError):
            resolve_window(anchor=date(2026, 8, 11), timezone="Asia/Singapore", start="Y-999999999", end="D")

    def test_calendar_group_count_is_bounded(self):
        from datetime import date, timedelta
        prototype = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=self.widgets["total"])[0]
        rows = [dict(prototype, accession=i, event_date=(date(2026, 1, 1) + timedelta(days=i)).isoformat())
                for i in range(101)]
        with self.assertRaises(views.OverrideRejectedError):
            self.payload("total", rows=rows, time_grouping="day")
