# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestMauticImportContacts(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company.write(
            {
                "mautic_api_url": "http://fake-mautic.com",
                "mautic_access_token": "token123",
            }
        )

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
            self.env["res.country.state"].create(
                {"name": "California", "code": "CA", "country_id": country.id}
            )
        partner_company = self.env["res.partner"].search(
            [("name", "=", "Test Company"), ("is_company", "=", True)], limit=1
        )
        if not partner_company:
            self.env["res.partner"].create({"name": "Test Company", "is_company": True})

    @patch(
        "odoo.addons.mautic_connector.models.res_company.ResCompany.refresh_token",
        return_value=None,
    )
    @patch(
        "odoo.addons.mautic_connector.models.res_partner.ResPartner.create_leads_from_segments_members",  # noqa: B950
        return_value=None,
    )
    @patch("requests.get")
    def test_import_contacts_success(self, mock_get, mock_leads, mock_refresh):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "contacts": {
                "1": {
                    "id": "5",
                    "fields": {
                        "core": {
                            "firstname": {"value": "John"},
                            "lastname": {"value": "Doe"},
                            "address1": {"value": "Street 123"},
                            "address2": {"value": "Apt 4"},
                            "mobile": {"value": "123456789"},
                            "phone": {"value": "987654321"},
                            "email": {"value": "john.doe@example.com"},
                            "zipcode": {"value": "12345"},
                            "city": {"value": "Blue Lake"},
                            "website": {"value": "http://johnswebsite.com"},
                            "position": {"value": "Manager"},
                            "country": {"value": "United States"},
                            "state": {"value": "California"},
                            "company": {"value": "Test Company"},
                        }
                    },
                    "mobile": None,
                },
                "2": {
                    "id": "2",
                    "fields": {
                        "core": {"firstname": {"value": ""}, "lastname": {"value": ""}}
                    },
                },
            }
        }
        mock_get.return_value = mock_response

        result = self.env["res.partner"].import_contacts()
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("type"), "ir.actions.client")
        self.assertEqual(result.get("tag"), "display_notification")
        msg = result.get("params", {}).get("message", "")
        self.assertIn("Total: 2 | Criadas: 1 | Atualizadas: 0 | Ignoradas: 0", msg)

        contact = self.env["res.partner"].search([("mautic_id", "=", "5")], limit=1)
        self.assertTrue(contact)
        self.assertEqual(contact.name, "John Doe")
        self.assertEqual(contact.email, "john.doe@example.com")
