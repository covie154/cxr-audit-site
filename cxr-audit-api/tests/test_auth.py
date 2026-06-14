import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(API_ROOT / "cxr_audit"))
os.chdir(API_ROOT)

from combined_server import api_app, api_auth_required, configured_cors_origins


class FastAPIAuthTests(unittest.TestCase):
    def test_auth_required_when_django_debug_false(self):
        with patch.dict(os.environ, {"DJANGO_DEBUG": "False"}, clear=False):
            self.assertTrue(api_auth_required())

    def test_auth_optional_in_debug_without_secret(self):
        with patch.dict(
            os.environ,
            {"DJANGO_DEBUG": "True", "API_REQUIRE_AUTH": "False", "API_SECRET_KEY": ""},
            clear=False,
        ):
            self.assertFalse(api_auth_required())

    def test_health_is_available_without_api_key(self):
        with patch.dict(os.environ, {"DJANGO_DEBUG": "False", "API_SECRET_KEY": ""}, clear=False):
            response = TestClient(api_app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_missing_required_secret_fails_closed(self):
        with patch.dict(os.environ, {"DJANGO_DEBUG": "False", "API_SECRET_KEY": ""}, clear=False):
            response = TestClient(api_app).get("/")

        self.assertEqual(response.status_code, 503)

    def test_invalid_key_is_forbidden(self):
        with patch.dict(
            os.environ,
            {"DJANGO_DEBUG": "False", "API_SECRET_KEY": "expected-secret"},
            clear=False,
        ):
            response = TestClient(api_app).get("/", headers={"X-API-Key": "wrong"})

        self.assertEqual(response.status_code, 403)

    def test_valid_key_is_allowed(self):
        with patch.dict(
            os.environ,
            {"DJANGO_DEBUG": "False", "API_SECRET_KEY": "expected-secret"},
            clear=False,
        ):
            response = TestClient(api_app).get("/", headers={"X-API-Key": "expected-secret"})

        self.assertEqual(response.status_code, 200)

    def test_production_cors_defaults_to_no_browser_origins(self):
        with patch.dict(
            os.environ,
            {"DJANGO_DEBUG": "False", "FASTAPI_CORS_ORIGINS": ""},
            clear=False,
        ):
            self.assertEqual(configured_cors_origins(), [])


if __name__ == "__main__":
    unittest.main()
