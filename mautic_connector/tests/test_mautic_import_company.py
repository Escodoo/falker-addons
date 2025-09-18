# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase


class TestMauticImportCompany(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company.write(
            {
                "mautic_api_url": "http://fake-mautic.com",
                "mautic_access_token": "token123",
            }
        )

    @patch(
        "odoo.addons.mautic_connector.models.res_company.ResCompany.refresh_token",
        return_value=None,
    )
    @patch("requests.get")
    def test_import_company_success(self, mock_get, _mock_refresh):
        page1 = MagicMock()
        page1.raise_for_status.return_value = None
        page1.json.return_value = {
            "companies": {
                "1": {
                    "id": 1,
                    "fields": {
                        "all": {
                            "companywebsite": "http://example.com",
                            "companyzipcode": "12345",
                            "companycity": "Monterey",
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
        page2 = MagicMock()
        page2.raise_for_status.return_value = None
        page2.json.return_value = {"companies": {}}
        mock_get.side_effect = [page1, page2]

        country = self.env["res.country"].search(
            [("name", "=", "United States")], limit=1
        )
        if not country:
            country = self.env["res.country"].create(
                {"name": "United States", "code": "US"}
            )
        state = self.env["res.country.state"].search(
            [("name", "=", "California"), ("country_id", "=", country.id)], limit=1
        )
        if not state:
            state = self.env["res.country.state"].create(
                {"name": "California", "code": "CA", "country_id": country.id}
            )
        result = self.env["res.partner"].import_company()
        self.assertIn("type", result)
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertIn("tag", result)
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("params", result)
        self.assertIn("message", result["params"])
        self.assertIn("Criadas: 1", result["params"]["message"])
        partner = self.env["res.partner"].search(
            [("mautic_id", "=", 1), ("is_company", "=", True)], limit=1
        )
        self.assertTrue(partner)
        self.assertEqual(partner.name, "Empresa Teste")
        self.assertEqual(partner.email, "contato@example.com")
        # self.assertEqual(partner.city, "Monterey")
        self.assertEqual(partner.state_id.id, state.id)
        self.assertEqual(partner.country_id.id, country.id)
        self.assertEqual(mock_get.call_count, 2)
