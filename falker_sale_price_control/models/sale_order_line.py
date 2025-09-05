from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Mirrors price_unit; editable only via inverse for permitted users.
    fiscal_price = fields.Float(
        compute="_compute_fiscal_price",
        inverse="_inverse_fiscal_price",
        store=True,  # Stored for reporting/performance
    )

    # ----------------------------
    # Compute / Inverse
    # ----------------------------
    @api.depends("price_unit")
    def _compute_fiscal_price(self):
        """
        Mirror price_unit into fiscal_price.
        Keep it pure: no writes, no early returns, no super() call.
        """
        for line in self:
            line.fiscal_price = line.price_unit

    def _inverse_fiscal_price(self):
        """
        If the user has the editor group, push fiscal_price -> price_unit.
        Otherwise, ignore edits and mirror back (fiscal_price := price_unit).
        Context guard is used to reduce re-entrancy risks if other modules
        override write().
        """
        can_edit = self.env.user.has_group(
            "falker_sale_price_control.group_price_editor"
        )

        if not can_edit:
            # Revert any attempted edit for non-permitted users
            for line in self:
                line.fiscal_price = line.price_unit
            return

        # Permitted users: assign price_unit from fiscal_price
        for line in self:
            # Guard context to avoid potential re-entrancy through other overrides
            line.with_context(skip_fiscal_sync=True).write(
                {"price_unit": line.fiscal_price}
            )
