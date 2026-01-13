# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

import requests

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
            }
        )

    @patch("odoo.addons.mautic_connector.models.res_company.requests.post")
    def test_refresh_token_is_updated_on_http_error(self, mock_post):
        self.assertEqual(self.company.mautic_refresh_token, "old_refresh")

        mock_response = mock_post.return_value
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "refresh_token": "new_refresh",
        }
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "400 Client Error: Bad Request for url"
        )

        with self.assertRaises(ValidationError):
            self.company.refresh_token()
            self.company.invalidate_cache()
            self.assertEqual(self.company.mautic_refresh_token, "new_refresh")
