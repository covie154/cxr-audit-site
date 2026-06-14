from django.test import SimpleTestCase, override_settings
from django.core.checks import run_checks


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
