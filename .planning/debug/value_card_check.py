"""Run against the local synthetic preview: python .planning/debug/value_card_check.py"""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    page.goto("http://127.0.0.1:8766/report/showcase/")
    page.locator('[data-type="value"] .widget-single-value').wait_for()
    for rows in (2, 3, 5):
        for columns in (2, 4, 12):
            page.locator('[data-type="value"]').evaluate('''(card, size) => {
                card.style.setProperty('--widget-rows', size.rows);
                card.style.gridColumn = 'span ' + size.columns;
            }''', {"rows": rows, "columns": columns})
            page.wait_for_timeout(150)
            assert page.locator('[data-type="value"] .widget-body').evaluate(
                '(body) => body.scrollHeight <= body.clientHeight && body.scrollWidth <= body.clientWidth'
            ), (rows, columns)
    page.goto("http://127.0.0.1:8766/layout/editor/showcase/")
    page.locator('.visual-card-actions').first.wait_for()
    assert page.locator('.visual-card:not([data-type="heading"]):not([data-type="divider"])').first.evaluate('''card => {
        const a = card.querySelector('.visual-card-actions').getBoundingClientRect();
        const c = card.getBoundingClientRect();
        const r = card.querySelector('.visual-resize').getBoundingClientRect();
        const icon = card.querySelector('.visual-icon').getBoundingClientRect();
        return Math.abs((a.left + a.right - c.left - c.right) / 2) < 1 && a.right <= r.left && a.top > icon.bottom;
    }''')
    browser.close()
print('Value cards fit both axes; editor actions are centred and clear of resize handle.')
