from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from report import urls as legacy_urls
from . import views


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
