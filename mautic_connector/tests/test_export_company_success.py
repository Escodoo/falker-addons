# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestExportCompany(TransactionCase):
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
            }
        )

        self.partner = self.env["res.partner"].create(
            {
                "name": "Empresa Teste",
                "phone": "123456789",
                "email": "empresa@teste.com",
                "website": "https://empresa.com",
                "street": "Rua 1",
                "street2": "Sala 2",
                "city": "São Paulo",
                "zip": "12345-678",
                "state_id": self.env.ref("base.state_br_sp").id,
                "country_id": self.env.ref("base.br").id,
                "company_type": "company",
            }
        )

    @patch("odoo.addons.mautic_connector.models.res_partner.requests.post")
    def test_export_company_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "company": {
                "id": 999,
                "name": "Empresa Teste",
            }
        }
        self.partner.export_company()
        self.assertEqual(self.partner.mautic_id, "999")
        self.assertTrue(self.partner.mautic_exported)
        log = self.env["mautic.sync.log"].search(
            [("sync_type", "=", "company"), ("state", "=", "done")], limit=1
        )
        self.assertTrue(log)
        self.assertIn("Empresa", log.log_detail)
