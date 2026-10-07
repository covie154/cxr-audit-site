# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Real Chromium checks with the existing synthetic-only throwaway server."""
import unittest
import yaml
from report_v2.tests import test_browser_layout as harness


@unittest.skipUnless(harness._PW_LAUNCH_OK, 'Playwright Chromium unavailable')
class VisualEditorBrowserTests(unittest.TestCase):
    setUpClass = classmethod(harness.BrowserLayoutTests.setUpClass.__func__)
    tearDownClass = classmethod(harness.BrowserLayoutTests.tearDownClass.__func__)

    def ready(self):
        self.page.wait_for_function("document.querySelector('[data-role=visual-status]').textContent === ''")

    def draft(self):
        return yaml.safe_load(self.page.locator('#id_yaml_text').input_value())

    def test_complete_visual_workflow(self):
        errors = []
        self.page.on('pageerror', lambda error: errors.append(str(error)))
        self.page.goto(self.server.base + '/layout/editor/browser_layout_14a/')
        self.ready()
        self.assertEqual(self.page.locator('.visual-card').count(), 4)
        original = self.page.locator('#id_yaml_text').input_value()
        select = self.page.locator('.visual-section-header select')
        select.select_option('text')
        form = self.page.locator('[data-role=card-options-form]')
        form.locator('[name=title]').fill('Synthetic note')
        form.locator('[name=text]').fill('Safe <script>text</script>\nSecond line')
        form.locator('[type=submit]').click()
        self.page.locator('[data-role=card-options]').wait_for(state='hidden')
        self.ready()
        self.assertEqual(self.page.locator('.visual-card').count(), 5)
        self.assertEqual(self.draft()['sections'][0]['widgets'][-1]['type'], 'text')
        note = self.page.locator('.visual-card').last
        note.hover(); note.locator('[data-visual-action=preview]').click()
        self.page.locator('[data-role=preview-dialog]').wait_for(state='visible')
        self.page.locator('[data-role=preview-output] .widget-static-text').wait_for(state='visible')
        self.assertIn('Safe <script>text</script>', self.page.locator('[data-role=preview-output]').inner_text())
        self.assertEqual(self.page.locator('[data-role=preview-output] script').count(), 0)
        self.page.locator('[data-action=close-preview]').click()
        self.page.locator('[data-visual-action=undo]').click(); self.ready()
        self.assertEqual(self.page.locator('#id_yaml_text').input_value(), original)

        # Guided edits and options Preview do not commit until Apply.
        first = self.page.locator('.visual-card').first
        first.hover(); first.locator('[data-visual-action=edit]').click()
        form.locator('[name=title]').fill('Unsaved preview title')
        form.locator('[name=width]').fill('6')
        form.locator('[data-visual-action=preview-options]').click()
        self.page.locator('[data-role=preview-output] .widget-frame').wait_for(state='visible')
        self.assertIn('Unsaved preview title', self.page.locator('[data-role=preview-output]').inner_text())
        self.assertEqual(self.page.locator('#id_yaml_text').input_value(), original)
        self.page.locator('[data-action=close-preview]').click()
        self.assertTrue(form.evaluate('(form) => form.checkValidity()'), form.evaluate('(form) => Array.from(form.elements).filter(el => el.validity && !el.validity.valid).map(el => [el.name, el.validationMessage])'))
        form.locator('[type=submit]').click()
        self.page.wait_for_function("!document.querySelector('[data-role=card-options]').open || document.querySelector('[data-role=card-form-error]').textContent")
        self.assertEqual(form.locator('[data-role=card-form-error]').inner_text(), '')
        self.page.locator('[data-role=card-options]').wait_for(state='hidden'); self.ready()
        self.assertEqual(self.draft()['sections'][0]['widgets'][0]['layout']['width'], 6)
        self.page.locator('[data-visual-action=undo]').click(); self.ready()

        # Snapped resize commits one change, then undo restores it.
        node = self.page.locator('.visual-card').first
        handle = node.locator('.visual-resize').bounding_box()
        grid = self.page.locator('.visual-grid').bounding_box()
        self.page.mouse.move(handle['x'] + 5, handle['y'] + 5)
        self.page.mouse.down(); self.page.mouse.move(handle['x'] + 5 + grid['width'] / 12, handle['y'] + 5, steps=5); self.page.mouse.up()
        self.ready()
        self.assertEqual(self.draft()['sections'][0]['widgets'][0]['layout']['width'], 4)
        self.page.locator('[data-visual-action=undo]').click(); self.ready()

        # Moving via a handle reorders within the section without changing identity.
        source = self.page.locator('.visual-card').first.locator('.visual-move').bounding_box()
        target = self.page.locator('.visual-card').nth(1).bounding_box()
        self.page.mouse.move(source['x'] + 5, source['y'] + 5); self.page.mouse.down()
        self.page.mouse.move(target['x'] + target['width'] - 20, target['y'] + 40, steps=8); self.page.mouse.up()
        self.ready()
        self.assertEqual(self.draft()['sections'][0]['widgets'][1]['id'], 'bv')
        self.page.locator('[data-visual-action=undo]').click(); self.ready()

        # Invalid manual YAML pauses the canvas; undo retains the original draft.
        self.page.locator('#yamlEditorTab').click()
        self.page.locator('#id_yaml_text').fill('invalid: [')
        self.page.wait_for_function("document.querySelector('[data-role=visual-status]').textContent.includes('paused')")
        self.page.locator('#visualEditorTab').click()
        self.assertTrue(self.page.locator('[data-role=visual-canvas]').evaluate('(node) => node.inert'))
        self.page.locator('[data-visual-action=undo]').click(); self.ready()
        self.assertEqual(self.page.locator('#id_yaml_text').input_value(), original)
        self.assertFalse(errors, errors)
        self.page.wait_for_function("document.querySelector('[data-role=validation-summary]').textContent === 'No errors'")
        self.page.screenshot(path=str(harness.DJANGO_APP.parent / '.planning/report-v2/visual-editor-execution/visual-editor.png'))

    def test_narrow_canvas_preserves_width_and_options_work(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.page.goto(self.server.base + '/layout/editor/browser_layout_14a/')
        self.ready()
        before = self.page.locator('#id_yaml_text').input_value()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 391)
        self.page.locator('.visual-card').first.click()
        self.page.locator('.visual-card').first.locator('[data-visual-action=edit]').click()
        self.assertEqual(self.page.locator('[name=width]').input_value(), '3')
        self.page.locator('[data-visual-action=cancel]').click()
        self.assertEqual(self.page.locator('#id_yaml_text').input_value(), before)
        self.page.set_viewport_size({'width': 1440, 'height': 900})
