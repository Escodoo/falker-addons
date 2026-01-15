# Copyright 2025 - TODAY, Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestMauticRefreshToken(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company.write(
            {
                "mautic_api_url": "https://mautic.example.com",
                "mautic_auth_base_url": "https://mautic.example.com",
                "mautic_client_id": "cid",
                "mautic_client_secret": "csec",
                "mautic_refresh_token": "old_refresh",
                "mautic_access_token": "old_access",
                "mautic_token_expires_at": fields.Datetime.now()
                - relativedelta(minutes=10),
            }
        )

    @patch("odoo.addons.mautic_connector.services.mautic_oauth_service.requests.post")
    def test_refresh_token_not_updated_on_http_error(self, mock_post):
        mock_response = mock_post.return_value
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"

        with self.assertRaises(ValidationError):
            self.company.refresh_token()

        self.company.invalidate_recordset()
        self.assertEqual(self.company.mautic_refresh_token, "old_refresh")
        self.assertEqual(self.company.mautic_access_token, "old_access")
        self.assertLess(
            self.company.mautic_token_expires_at,
            fields.Datetime.now(),
        )

    @patch("odoo.addons.mautic_connector.services.mautic_oauth_service.requests.post")
    def test_refresh_token_updated_on_success(self, mock_post):
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        }

        token = self.company.refresh_token()

        self.company.invalidate_recordset()

        self.assertEqual(token, "new_access")
        self.assertEqual(self.company.mautic_access_token, "new_access")
        self.assertEqual(self.company.mautic_refresh_token, "new_refresh")
        self.assertGreater(
            self.company.mautic_token_expires_at,
            fields.Datetime.now(),
        )
