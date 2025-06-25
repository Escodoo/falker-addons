from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    fiscal_price = fields.Float(
        string="Preço Fiscal",
        compute="_compute_fiscal_price",
        store=True,
        readonly=True,
        help="Preço fiscal calculado automaticamente (inclui impostos brasileiros)."
    )

    @api.depends('price_unit', 'fiscal_tax_ids', 'product_id')
    def _compute_fiscal_price(self):
        for line in self:
            if hasattr(super(), '_compute_fiscal_price'):
                super(SaleOrderLine, line)._compute_fiscal_price()
            else:
                line.fiscal_price = line.price_unit

