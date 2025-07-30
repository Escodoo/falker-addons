# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMauticController(HttpCase):
    def setUp(self):
        super().setUp()

        self.company = self.env.ref("base.main_company")
        self.company.mautic_api_url = "http://fake-mautic.com"
        self.company.mautic_client_id = "abc123"
        self.company.mautic_client_secret = "secret123"
        self.company.mautic_request_token_url = "http://fake-mautic.com/redirect"
        self.env.user.company_id = self.company

    @patch("requests.post")
    def test_get_auth_code_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"access_token": "token123"}

        response = self.url_open(
            "/get_auth_code?code=test_code",
            timeout=20,
        )
        self.assertIn(b"Successfully connected, please close this window.", response)

        self.assertEqual(self.company.mautic_access_token, "token123")
        self.assertEqual(self.company.mautic_auth_code, "test_code")
        self.assertEqual(self.company.mautic_client_id, "abc123")
        self.assertEqual(self.company.mautic_client_secret, "secret123")

    def test_get_auth_code_missing_code(self):
        response = self.url_open("/get_auth_code", timeout=20)
        self.assertIn("Code not received from Mautic.", response.text)
