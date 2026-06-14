from django.contrib import admin
from django.test import TestCase, override_settings

from .admin import AuditEventAdmin
from .models import AuditEvent


@override_settings(DATABASE_ROUTERS=["lunit_audit.dbrouters.AuditRouter"])
class AuditFoundationTests(TestCase):
    databases = {"default", "audit"}

    def test_category_choices_include_required_phase_one_categories(self):
        values = {choice[0] for choice in AuditEvent.Category.choices}

        self.assertIn("UserSelected", values)
        self.assertIn("FileUpload", values)
        self.assertIn("LLMCall", values)
        self.assertIn("LLMSuccess", values)
        self.assertIn("LLMFailure", values)

    def test_audit_events_write_to_audit_database(self):
        event = AuditEvent.objects.using("audit").create(
            username="auditor",
            category=AuditEvent.Category.USER_SELECTED,
            action="GET /view/",
            metadata={"route": "/view/"},
        )

        self.assertEqual(AuditEvent.objects.using("audit").count(), 1)
        self.assertEqual(event.metadata["route"], "/view/")

    def test_audit_schema_avoids_patient_name_and_report_text_fields(self):
        field_names = {field.name for field in AuditEvent._meta.fields}

        self.assertNotIn("patient_name", field_names)
        self.assertNotIn("report_text", field_names)
        self.assertNotIn("text_report", field_names)

    def test_admin_is_read_only(self):
        model_admin = AuditEventAdmin(AuditEvent, admin.site)

        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))
