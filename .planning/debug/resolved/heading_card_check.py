"""Run: python .planning/debug/resolved/heading_card_check.py"""
from pathlib import Path
from playwright.sync_api import sync_playwright

css = (Path(__file__).resolve().parents[3] / "django-app/report_v2/static/report_v2/report.css").read_text(encoding="utf-8")
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page()
    for width in (1360, 390):
        page.set_viewport_size({"width": width, "height": 800})
        for columns in (3, 12):
            page.set_content('<style>* { box-sizing: border-box; } body { margin: 0; font: 16px/1.5 sans-serif; } h2 { font-size: 24px; } .card { border: 1px solid transparent; }</style><style>' + css + '</style><main class="report-v2-page"><div class="report-grid"><article class="card widget-frame" data-type="heading" style="grid-column: span ' + str(columns) + '; --widget-rows: 1"><h2>Summary</h2><div class="widget-body"></div></article></div></main>')
            card = page.locator('.widget-frame')
            assert card.evaluate('(el) => el.scrollHeight <= el.clientHeight && el.scrollWidth <= el.clientWidth'), (width, columns)
            assert page.locator('h2').evaluate('(el) => getComputedStyle(el).fontSize') == '20px'
    browser.close()
print('Heading fits one row without scrolling at desktop/mobile widths.')

