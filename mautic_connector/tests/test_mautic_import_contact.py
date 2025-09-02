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
        self.company.mautic_api_url = "http://fake-mautic.com"
        self.company.mautic_access_token = "token123"

    @patch("requests.get")
    def test_import_contacts_success(self, mock_get):
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
                        "core": {
                            "firstname": {"value": ""},
                            "lastname": {"value": ""},
                        }
                    },
                },
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
        partner = self.env["res.partner"].search(
            [("name", "=", "Test Company")], limit=1
        )
        if not partner:
            partner = self.env["res.partner"].create({"name": "Test Company"})
        result = self.company.import_contacts()

        self.assertIn("type", result)
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertIn("tag", result)
        self.assertEqual(result["tag"], "display_notification")
        self.assertIn("params", result)
        self.assertIn(
            "Total: 2 | Criadas: 1 | Atualizadas: 0 | Ignoradas (nome): 0",
            result["params"]["message"],
        )

        contact = self.env["res.partner"].search([("mautic_id", "=", "5")], limit=1)
        self.assertTrue(contact)
        self.assertEqual(contact.name, "John Doe")
        self.assertEqual(contact.email, "john.doe@example.com")
