# Copyright 2024 - TODAY, Kaynnan Lemes <kaynnan.lemes@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class L10nBrCoaGeneric(TransactionCase):
    def setUp(self):
        super().setUp()

        self.l10n_br_coa_generic = self.env.ref(
            "l10n_br_coa_falker.falker_coa_template"
        )
        self.l10n_br_company = self.env["res.company"].create(
            {"name": "Empresa Falker - Plano de Contas"}
        )

    def test_l10n_br_coa_generic(self):
        """Test to install the chart of accounts template in a new company"""
        self.env.user.company_ids += self.l10n_br_company
        self.env.user.company_id = self.l10n_br_company
        self.l10n_br_coa_generic.try_loading()

        self.assertEqual(
            self.l10n_br_coa_generic, self.l10n_br_company.chart_template_id
        )
