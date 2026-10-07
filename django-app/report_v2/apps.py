import mimetypes

from django.apps import AppConfig


class ReportV2Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "report_v2"
    verbose_name = "Report v2"

    def ready(self):
        # Windows registry MIME entries can classify ES modules as text/plain.
        mimetypes.add_type("text/javascript", ".mjs")
