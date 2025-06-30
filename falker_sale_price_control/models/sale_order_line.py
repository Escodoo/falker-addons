from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    fiscal_price = fields.Float(
        string="Preço Fiscal",
        compute="_compute_fiscal_price",
        store=True,
    )

    @api.depends("price_unit", "fiscal_tax_ids", "product_id", "order_id.pricelist_id")
    def _compute_fiscal_price(self):
        for line in self:
            if hasattr(super(), "_compute_fiscal_price"):
                super(SaleOrderLine, line)._compute_fiscal_price()
            else:
                line.fiscal_price = line.price_unit

    @api.model
    def create(self, values):
        return super().create(values)

    def write(self, vals):
        # Checks if the order has a different pricelist from the one in the context
        if "pricelist_id" not in vals and any(
            line.order_id.pricelist_id.id
            != self.env.context.get("default_pricelist_id")
            for line in self
            if line.order_id
        ):
            vals["price_unit"] = self._get_price_from_pricelist()

        # Att when change the product
        if "product_id" in vals:
            for line in self:
                order = line.order_id
                product = self.env["product.product"].browse(vals["product_id"])
                quantity = vals.get("product_uom_qty", line.product_uom_qty)

                if order.pricelist_id:
                    price = order.pricelist_id.with_context(
                        uom=product.uom_id.id, date=order.date_order
                    ).get_product_price(product, quantity, order.partner_id)

                    vals["price_unit"] = price
                    vals["fiscal_price"] = price

        return super().write(vals)

    def _get_price_from_pricelist(self):
        """Obtém o preço atualizado da lista de preços com tratamento para linhas vazias"""
        self.ensure_one()

        # If it's a line without product, return 0
        if not self.product_id or self.display_type == "line_note":
            return 0.0

        return self.order_id.pricelist_id.with_context(
            uom=self.product_uom.id, date=self.order_id.date_order
        ).get_product_price(
            self.product_id, self.product_uom_qty, self.order_id.partner_id
        )

    @api.onchange("product_id")
    def _onchange_product_id_custom_price(self):
        if not self.product_id:
            return
        self.product_id_change()
        self._compute_tax_id()
