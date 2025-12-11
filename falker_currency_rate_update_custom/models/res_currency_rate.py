# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResCurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    rate_purchase = fields.Float(
        string="Purchase Rate (BCB)",
    )
