from pathlib import Path
import re
from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django.template.loader import render_to_string

from report import urls as legacy_urls
from .. import views


@override_settings(STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ReportRoutingTests(SimpleTestCase):
    def test_report_routes_are_separate(self):
        self.assertEqual(reverse("report_v2:index"), "/report/")
        self.assertEqual(reverse("report:index"), "/report-old/")
        self.assertEqual(resolve("/report/").func, views.index)
        for route in legacy_urls.urlpatterns:
            self.assertTrue(reverse(f"report:{route.name}").startswith("/report-old/"))

    def test_both_reports_require_login(self):
        for url in ("/report/", "/report-old/"):
            request = RequestFactory().get(url)
            request.user = AnonymousUser()
            response = resolve(url).func(request)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/?next=", response.url)

    def test_v2_renders_without_database_access(self):
        request = RequestFactory().get("/report/")
        request.user = Mock(is_authenticated=True, is_superuser=False, username="reviewer")
        request.user.groups.filter.return_value.exists.return_value = False
        request.resolver_match = resolve("/report/")
        response = views.index(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in ('href="/report-old/"', 'href="/report/"', 'data-report-chart', 'No study data', 'echarts.min.js', 'aria-current="page"'):
            self.assertIn(marker, html)

    def test_static_assets_are_discoverable(self):
        for asset in ("report.js", "report.css", "vendor/echarts.min.js"):
            self.assertIsNotNone(finders.find(f"report_v2/{asset}"))

    def test_report_sidebar_items_have_independent_active_states(self):
        for url, active_label in (("/report/", "Report V2"), ("/report-old/", "Report V1")):
            request = RequestFactory().get(url)
            request.user = Mock(is_authenticated=True, is_superuser=False, username="reviewer")
            request.resolver_match = resolve(url)
            html = render_to_string("base.html", {"user": request.user}, request=request)
            links = re.findall(r'<a href="(/report(?:-old)?/)"[^>]*>.*?</a>', html, re.S)
            self.assertEqual(set(links), {"/report/", "/report-old/"})
            active = re.search(r'<a href="/report(?:-old)?/"[^>]*aria-current="page"[^>]*>(.*?)</a>', html, re.S)
            self.assertIsNotNone(active)
            self.assertIn(active_label, active.group(1))
        source = Path(__file__).resolve().parent.parent / "templates" / "report_v2"
        for name in ("index.html", "page.html"):
            self.assertNotIn('class="report-v2-legacy"', (source / name).read_text())

    def test_card_settings_only_render_for_non_value_widgets_at_least_three_columns_wide(self):
        for kind, width, expected in (("value", 12, False), ("table", 2, False), ("bar", 1, False), ("table", 3, True), ("bar", 6, True)):
            with self.subTest(kind=kind, width=width):
                widget = {"type": kind, "layout": {"width": width}, "controls": {"date_range": True}}
                frame = {"id": "sample", "type": kind, "width": width, "controls": views._allowed_controls(widget)}
                html = render_to_string("report_v2/page.html", {"slug": "sample", "sections_ctx": [{"widgets": [frame]}]})
                self.assertEqual('data-role="controls"' in html, expected)
                self.assertEqual('data-action="apply"' in html, expected)
