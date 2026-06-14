import os
from unittest.mock import patch

from django.test import SimpleTestCase

from .views import get_api_headers


class APIHeaderTests(SimpleTestCase):
    def test_api_secret_key_is_forwarded_when_configured(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": "shared-secret"}, clear=False):
            self.assertEqual(get_api_headers(), {"X-API-Key": "shared-secret"})

    def test_api_secret_header_is_omitted_when_unset(self):
        with patch.dict(os.environ, {"API_SECRET_KEY": ""}, clear=False):
            self.assertEqual(get_api_headers(), {})
