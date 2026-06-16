import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .views import get_api_headers


class APIHeaderTests(SimpleTestCase):
    def test_api_secret_key_is_forwarded_when_configured(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "shared-secret"}, clear=False):
            self.assertEqual(get_api_headers(), {"X-API-Key": "shared-secret"})

    def test_api_secret_header_is_omitted_when_unset(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": ""}, clear=False):
            self.assertEqual(get_api_headers(), {})


class PostgresMigrationCommandTests(SimpleTestCase):
    databases = {"default", "audit"}

    def test_prepare_postgres_migration_dry_run_lists_both_aliases(self):
        out = StringIO()

        call_command("prepare_postgres_migration", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("[default]", output)
        self.assertIn("[audit]", output)
        self.assertIn("dumpdata --database default", output)
        self.assertIn("dumpdata --database audit", output)
        self.assertIn("synthetic or explicitly approved non-PHI data", output)

    def test_prepare_postgres_migration_refuses_export_without_approval(self):
        with self.assertRaises(CommandError):
            call_command("prepare_postgres_migration")

    def test_validate_postgres_migration_dry_run_outputs_validation_plan(self):
        out = StringIO()

        call_command("validate_postgres_migration", "--dry-run", "--include-audit", stdout=out)

        output = out.getvalue()
        self.assertIn("Validation checks beyond row counts", output)
        self.assertIn("Audit alias checks", output)
        self.assertIn("Managed model inventory", output)
