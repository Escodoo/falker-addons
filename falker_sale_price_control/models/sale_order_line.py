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

    def write(self, vals):
        if self.env.user.has_group("falker_sale_price_control.group_price_editor"):
            # Users with permission - price synchronization
            if "price_unit" in vals:
                vals["fiscal_price"] = vals["price_unit"]
            elif "fiscal_price" in vals:
                vals["price_unit"] = vals["fiscal_price"]
        else:
            # Users without permission - apply rules
            if "pricelist_id" not in vals and any(
                line.order_id.pricelist_id.id
                != self.env.context.get("default_pricelist_id")
                for line in self
                if line.order_id
            ):
                vals["price_unit"] = self._get_price_from_pricelist()

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
        """Get price from price list"""
        self.ensure_one()

        if not self.product_id or self.display_type == "line_note":
            return 0.0

        return self.order_id.pricelist_id.with_context(
            uom=self.product_uom.id, date=self.order_id.date_order
        ).get_product_price(
            self.product_id, self.product_uom_qty, self.order_id.partner_id
        )

    @api.onchange("product_id", "product_uom_qty")
    def _onchange_product_quantity(self):
        """Att price when change product or quantity"""
        if not self.env.user.has_group("falker_sale_price_control.group_price_editor"):
            if self.product_id:
                price = self._get_price_from_pricelist()
                self.price_unit = price
                self.fiscal_price = price

        # Onchange original from Odoo
        if hasattr(super(), "product_id_change"):
            super().product_id_change()
        self._compute_tax_id()
