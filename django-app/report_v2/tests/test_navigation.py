from unittest import mock
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from report_v2.models import ReportPreference


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ReportNavigationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="report-reader")
        self.other = User.objects.create_user(username="other-reader")
        self.client.force_login(self.user)
        reports = [{"slug": slug, "title": title, "version": slug+"@r1", "section_count": 1}
                   for slug, title in (("first", "First report"), ("second", "Second report"))]
        patcher = mock.patch("report_v2.data.list_published", return_value=reports)
        patcher.start(); self.addCleanup(patcher.stop)
        self.reports = reports

    def test_list_default_and_back_to_list_are_user_specific(self):
        with mock.patch("report_v2.data.fetch_project_rows", side_effect=AssertionError("list must not read studies")):
            response = self.client.get("/report/")
            self.assertContains(response, "First report")
            self.assertContains(response, "Second report")
            self.assertNotContains(response, "Report V2")
            self.assertNotContains(response, "data-report-chart")
            self.assertEqual(self.client.post("/report/preferences/default/", {"slug": "second", "user": self.other.pk}).status_code, 302)
            self.assertEqual(ReportPreference.objects.get(user=self.user).default_slug, "second")
            self.assertFalse(ReportPreference.objects.filter(user=self.other).exists())
            self.assertRedirects(self.client.get("/report/"), "/report/second/", fetch_redirect_response=False)
            self.assertContains(self.client.get("/report/?list=1"), "Clear default")
            self.client.force_login(self.other)
            self.assertEqual(self.client.get("/report/").status_code, 200)
            self.client.force_login(self.user)
            self.client.post("/report/preferences/default/", {"slug": ""})
            self.assertEqual(self.client.get("/report/").status_code, 200)

    def test_unknown_or_unpublished_default_never_opens(self):
        self.assertEqual(self.client.post("/report/preferences/default/", {"slug": "../draft"}).status_code, 400)
        self.assertFalse(ReportPreference.objects.exists())
        ReportPreference.objects.create(user=self.user, default_slug="unpublished")
        self.assertEqual(self.client.get("/report/").status_code, 200)

    def test_default_changes_require_login_post_and_csrf(self):
        anonymous = Client()
        self.assertEqual(anonymous.post("/report/preferences/default/", {"slug": "first"}).status_code, 302)
        self.assertEqual(self.client.get("/report/preferences/default/").status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post("/report/preferences/default/", {"slug": "first"}).status_code, 403)
        strict.get("/report/?list=1")
        token = strict.cookies["csrftoken"].value
        self.assertEqual(strict.post("/report/preferences/default/", {"slug": "first"}, headers={"X-CSRFToken": token}).status_code, 302)
