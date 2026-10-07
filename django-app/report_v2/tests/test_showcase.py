from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from report_v2 import data, views
from report_v2.definitions.loader import load_report_definition
from report_v2.definitions.repository import DefinitionRepository
from report_v2.projects.prime import get_project_definition
from report_v2.tests import test_seed


class ShowcaseTests(SimpleTestCase):
    def setUp(self):
        self.text = (Path(__file__).resolve().parents[1] / "seed/showcase.v1.yaml").read_text(encoding="utf-8")
        self.layout = load_report_definition(self.text)

    def test_all_seven_cards_publish_and_evaluate_through_existing_project(self):
        widgets = views._layout_widgets(self.layout)
        self.assertEqual({w["type"] for w in widgets.values()}, {"value", "table", "line", "bar", "pie", "confusion_matrix", "boxplot"})
        with TemporaryDirectory() as root:
            DefinitionRepository(root=root, project_id="prime").publish("showcase", self.text)
        for widget in widgets.values():
            for field in ("", "site", "age"):
                rows = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)
                payload = views._evaluate(self.layout, widget, rows=rows, comparison=field, grouping=[field] if field else [])
                self.assertNotIn("error", payload, (widget["id"], field))
                self.assertFalse(payload["empty"])
                if widget["type"] == "bar": self.assertTrue(payload["series"])
                if widget["type"] == "pie": self.assertTrue(payload["categories"])
                if widget["type"] == "confusion_matrix": self.assertEqual(payload["classes"], ["0", "1"])

    def test_real_adapter_maps_category_source_and_single_class_matrix(self):
        row = {}
        data._map_inputs(row, SimpleNamespace(**{get_project_definition().source("llm_abnormal").field: 1}), {"category": "llm_abnormal"}, "categorical_count", get_project_definition())
        self.assertEqual(row["category"], 1)
        widget = views._layout_widgets(self.layout)["matrix"]
        rows = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)
        for entry in rows: entry.update(gt_label=True, pred_label=1)
        payload = views._evaluate(self.layout, widget, rows=rows)
        self.assertNotIn("error", payload)
        self.assertEqual(payload["classes"], ["0", "1"])

    def test_calendar_grouping_renders_all_seven_card_contracts(self):
        from report_v2.exports import _widget_tables
        for widget in views._layout_widgets(self.layout).values():
            rows = test_seed.SeedSynthEvaluationTests._fake_fetch(layout_widget=widget)
            for i, row in enumerate(rows):
                row["event_date"] = "2026-08-03" if i % 2 else "2026-08-11"
            payload = views._evaluate(self.layout, widget, rows=rows, time_grouping="week")
            self.assertNotIn("error", payload)
            if widget["type"] == "line":
                self.assertTrue(payload["series"])
            else:
                self.assertEqual(len(payload["time_groups"]), 2, widget["id"])
                self.assertTrue(_widget_tables(payload))
                for group in payload["time_groups"]:
                    self.assertEqual(group["payload"]["dates"]["anchor_date"], payload["dates"]["anchor_date"])
