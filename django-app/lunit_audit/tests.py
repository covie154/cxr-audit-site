from django.core.checks import run_checks
from django.test import SimpleTestCase, override_settings

from . import settings


class TransportSecurityCheckTests(SimpleTestCase):
    def test_http_llm_transport_warns_in_production_without_allowance(self):
        with override_settings(
            DEBUG=False,
            LLM_BASE_URL="http://llm.internal:11434/v1",
            LLM_ALLOW_INSECURE_TRANSPORT=False,
        ):
            warning_ids = {message.id for message in run_checks()}

        self.assertIn("lunit_audit.W002", warning_ids)

    def test_https_llm_transport_does_not_warn(self):
        with override_settings(
            DEBUG=False,
            LLM_BASE_URL="https://llm.internal/v1",
            LLM_ALLOW_INSECURE_TRANSPORT=False,
        ):
            warning_ids = {message.id for message in run_checks()}

        self.assertNotIn("lunit_audit.W001", warning_ids)
        self.assertNotIn("lunit_audit.W002", warning_ids)


class DatabaseSettingsTests(SimpleTestCase):
    def test_database_config_defaults_to_sqlite(self):
        config = settings.database_config()

        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertTrue(str(config["NAME"]).endswith("db.sqlite3"))

    @override_settings()
    def test_database_config_supports_postgres_env(self):
        env = {
            "DATABASE_ENGINE": "postgres",
            "DATABASE_NAME": "primer_app",
            "DATABASE_USER": "primer_user",
            "DATABASE_PASSWORD": "placeholder",
            "DATABASE_HOST": "postgres",
            "DATABASE_PORT": "5432",
            "DATABASE_SSLMODE": "require",
            "DATABASE_CONN_MAX_AGE": "60",
            "DATABASE_CONN_HEALTH_CHECKS": "True",
        }
        with override_environ(env):
            config = settings.database_config()

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "primer_app")
        self.assertEqual(config["USER"], "primer_user")
        self.assertEqual(config["PASSWORD"], "placeholder")
        self.assertEqual(config["HOST"], "postgres")
        self.assertEqual(config["PORT"], "5432")
        self.assertEqual(config["OPTIONS"], {"sslmode": "require"})
        self.assertEqual(config["CONN_MAX_AGE"], 60)
        self.assertTrue(config["CONN_HEALTH_CHECKS"])

    def test_audit_database_config_supports_separate_postgres_database(self):
        env = {
            "AUDIT_DATABASE_ENGINE": "postgres",
            "AUDIT_DATABASE_NAME": "primer_audit",
            "AUDIT_DATABASE_USER": "audit_user",
            "AUDIT_DATABASE_PASSWORD": "placeholder",
            "AUDIT_DATABASE_HOST": "postgres",
            "AUDIT_DATABASE_PORT": "5432",
        }
        with override_environ(env):
            config = settings.audit_database_config()

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "primer_audit")
        self.assertEqual(config["USER"], "audit_user")
        self.assertEqual(config["HOST"], "postgres")


class override_environ:
    def __init__(self, values):
        self.values = values
        self.original = {}

    def __enter__(self):
        import os

        for key, value in self.values.items():
            self.original[key] = os.environ.get(key)
            os.environ[key] = value

    def __exit__(self, exc_type, exc, tb):
        import os

        for key, value in self.original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
