# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Synthetic regression checks for authoritative YAML transformations and static outputs."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.template.loader import render_to_string

from report_v2 import admin_views, views, exports
from report_v2.definitions import visual
from report_v2.definitions.loader import DefinitionError, load_report_definition
from report_v2.tests.test_editor import VALID_YAML, _SETTINGS


@override_settings(**_SETTINGS)
class VisualEditorTests(SimpleTestCase):
    def operation(self, action, **kwargs):
        return visual.transform(VALID_YAML, {'action': action, 'section_id': 's', 'widget_id': 'w', **kwargs})

    def test_transform_is_validated_and_preserves_unrelated_fields(self):
        original = load_report_definition(VALID_YAML)
        card = deepcopy(original['sections'][0]['widgets'][0])
        card['title'] = 'Edited'; card['layout']['width'] = 6
        text, doc = self.operation('edit', card=card)
        self.assertEqual(doc['sections'][0]['widgets'][0]['query'], original['sections'][0]['widgets'][0]['query'])
        self.assertEqual(doc['id'], original['id'])
        self.assertEqual(load_report_definition(text), doc)
        with self.assertRaises((DefinitionError, ValueError)):
            self.operation('resize', layout={'width': 13, 'height': 2})
        with self.assertRaises(ValueError):
            self.operation('delete')
        with self.assertRaises(ValueError):
            self.operation('edit', card={**card, 'id': 'other'})
        with self.assertRaises(ValueError):
            self.operation('move', index=True)
        with self.assertRaises(ValueError):
            self.operation('move', index=0, section_id='other')

    def test_add_move_delete_and_static_schema(self):
        text, doc = self.operation('add', card={'title': 'Note', 'type': 'text', 'text': '<script>alert(1)</script>\nNext line', 'layout': {'width': 12, 'height': 2}})
        card_id = doc['sections'][0]['widgets'][-1]['id']
        moved, doc = visual.transform(text, {'action': 'move', 'section_id': 's', 'widget_id': card_id, 'index': 0})
        self.assertEqual(doc['sections'][0]['widgets'][0]['id'], card_id)
        removed, doc = visual.transform(moved, {'action': 'delete', 'section_id': 's', 'widget_id': card_id})
        self.assertEqual(doc, load_report_definition(VALID_YAML))
        bad = yaml.safe_load(text); bad['sections'][0]['widgets'][-1]['query'] = {'measurement': 'record_count', 'inputs': {}}
        with self.assertRaises(DefinitionError):
            load_report_definition(yaml.safe_dump(bad))

    def test_trust_boundary_and_no_persistence(self):
        request = RequestFactory().post('/layout/actions/visual/', {'yaml_text': VALID_YAML})
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=False, groups=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(exists=lambda: False)))
        self.assertEqual(admin_views.editor_visual(request).status_code, 403)
        request.user.is_superuser = True
        request._dont_enforce_csrf_checks = True
        with patch.object(admin_views, '_repository', side_effect=AssertionError('must not persist')):
            response = admin_views.editor_visual(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['yaml_text'], VALID_YAML)
        self.assertIn('catalog', json.loads(response.content))
        request = RequestFactory().post('/layout/actions/visual/', {'yaml_text': VALID_YAML, 'operation': '{bad'})
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=True)
        request._dont_enforce_csrf_checks = True
        self.assertEqual(admin_views.editor_visual(request).status_code, 422)

    def test_invalid_dynamic_options_are_rejected(self):
        card = load_report_definition(VALID_YAML)['sections'][0]['widgets'][0]
        card['query']['measurement'] = 'made_up'
        with self.assertRaises(ValueError): self.operation('edit', card=card)
        card['query']['measurement'] = 'record_count'; card['ci'] = {'enabled': True, 'method': 'wilson'}
        with self.assertRaises(ValueError): self.operation('edit', card=card)

    def test_static_cards_never_fetch_rows_and_outputs_escape_text(self):
        card = {'id': 'note', 'title': 'Note', 'type': 'text', 'text': '<script>alert(1)</script>\nNext line', 'layout': {'width': 12, 'height': 2}}
        with patch.object(views.data, 'fetch_project_rows', side_effect=AssertionError('no clinical read')):
            payload = views._evaluate({}, card)
        document = {'slug': 'test', 'version': 'r1', 'title': 'Test', 'widgets': [{'widget_id': 'note', 'title': 'Note', 'type': 'text', 'payload': payload}]}
        vm = exports._print_view_model(document)
        for template, context in [('print', {'print': vm}), ('email', {'email': exports._email_view_model(document, {})})]:
            body = render_to_string('report_v2/' + template + '.html', context)
            self.assertIn('&lt;script&gt;', body)
            self.assertNotIn('<script>alert', body)
        self.assertIn(card['text'], exports._email_text(exports._email_view_model(document, {}), '', 'Test'))
        self.assertIn('&lt;script&gt;', render_to_string('report_v2/_widget_card.html', {'f': {'type': 'text', 'title': 'Note', 'payload': payload}}))

    def test_mixed_static_and_dynamic_report_evaluates_without_static_queries(self):
        text, document = self.operation('add', card={
            'title': 'Divider', 'type': 'divider', 'layout': {'width': 12, 'height': 1},
        })
        dynamic, divider = document['sections'][0]['widgets']
        with patch.object(views.data, 'fetch_project_rows', side_effect=AssertionError('no clinical read')):
            result = views._evaluate(document, dynamic, rows=[])
            static_result = views._evaluate(document, divider)
        self.assertNotIn('error', result)
        self.assertEqual(static_result['static_type'], 'divider')
        vm = exports._print_view_model({'widgets': [{
            'widget_id': divider['id'], 'title': divider['title'], 'type': 'divider', 'payload': static_result,
        }]})
        self.assertIn('<hr>', render_to_string('report_v2/print.html', {'print': vm}))

    def test_add_card_inserts_at_row_end_and_rejects_invalid_position(self):
        card = {'title': 'Note', 'type': 'text', 'text': 'Synthetic', 'layout': {'width': 2, 'height': 3}}
        text, document = self.operation('add', card=card, index=0)
        self.assertEqual([w['id'] for w in document['sections'][0]['widgets']], ['card_1', 'w'])
        for index in (-1, 2, True):
            with self.assertRaises(ValueError):
                self.operation('add', card=card, index=index)
