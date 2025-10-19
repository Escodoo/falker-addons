# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestExportCustomer(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.ref("base.main_company")
        self.company.write(
            {
                "mautic_access_token": "test_token",
                "mautic_api_url": "http://testmautic.com",
                "mautic_auth_base_url": "http://testmautic.com",
                "mautic_client_id": "cid",
                "mautic_client_secret": "csec",
                "mautic_refresh_token": "rftok",
            }
        )

        self.partner = self.env["res.partner"].create(
            {
                "name": "João Pedro Silva",
                "email": "joao@example.com",
                "street": "Rua Teste",
                "street2": "Apto 101",
                "city": "São Paulo",
                "state_id": self.env.ref("base.state_br_sp").id,
                "country_id": self.env.ref("base.br").id,
                "zip": "12345-678",
                "phone": "11999999999",
                "company_id": self.company.id,
            }
        )

    @patch(
        "odoo.addons.mautic_connector.models.res_company.ResCompany.refresh_token",
        return_value=None,
    )
    @patch("odoo.addons.mautic_connector.models.res_partner.requests.post")
    def test_export_contact_success(self, mock_post_partner, _mock_refresh):
        mock_response = {"contact": {"id": 1234}}

        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = mock_response

            self.partner.export_contact()
            self.assertEqual(self.partner.mautic_id, "1234")
            self.assertTrue(self.partner.mautic_exported)
