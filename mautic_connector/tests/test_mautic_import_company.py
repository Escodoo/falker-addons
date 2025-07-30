# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestMauticImportCompany(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company.mautic_api_url = "http://fake-mautic.com"
        self.company.mautic_access_token = "token123"

    @patch("requests.get")
    def test_import_company_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "companies": {
                "1": {
                    "id": "1",
                    "fields": {
                        "all": {
                            "companywebsite": "http://example.com",
                            "companyzipcode": "12345",
                            "companycity": "Cidade Teste",
                            "companyaddress1": "Rua Teste",
                            "companyaddress2": "Apto 101",
                            "companycountry": "United States",
                            "companystate": "California",
                        },
                        "core": {
                            "companyemail": {"value": "contato@example.com"},
                            "companyname": {"value": "Empresa Teste"},
                        },
                    },
                }
            }
        }
        mock_get.return_value = mock_response

        country = self.env["res.country"].search(
            [("name", "=", "United States")], limit=1
        )
        if not country:
            country = self.env["res.country"].create(
                {"name": "United States", "code": "US"}
            )
        state = self.env["res.country.state"].search(
            [("name", "=", "California")], limit=1
        )
        if not state:
            state = self.env["res.country.state"].create(
                {"name": "California", "code": "CA", "country_id": country.id}
            )
        result = self.company.import_company()

        self.assertIn("type", result)
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertIn("tag", result)
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("params", result)
        self.assertIn("message", result["params"])
        self.assertIn("Sucesso: 1", result["params"]["message"])

        partner = self.env["res.partner"].search(
            [("mautic_company_id", "=", "1")], limit=1
        )
        self.assertTrue(partner)
        self.assertEqual(partner.name, "Empresa Teste")
        self.assertEqual(partner.email, "contato@example.com")
        self.assertEqual(partner.city, "Cidade Teste")
        self.assertEqual(partner.state_id, state)
        self.assertEqual(partner.country_id, country)
