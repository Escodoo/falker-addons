from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSaleOrderLinePriceControl(TransactionCase):
    """
    Single test suite covering both the core purpose (minimal)
    and optional scenarios (pricelist interactions), without
    asserting core sale pricing numbers. Focus:
      - fiscal_price mirrors price_unit
      - inverse only for users in editor group
      - no side effects with taxes/confirmation/pricelists
    """

    def setUp(self):
        super().setUp()

        # --- Partner ---
        self.partner = self.env["res.partner"].create({"name": "Test Partner"})

        # --- Taxes (just to ensure no side effects on mirror) ---
        self.tax = self.env["account.tax"].create(
            {"name": "Tax 10%", "amount": 10.0, "type_tax_use": "sale"}
        )

        # --- Products ---
        self.product = self.env["product.product"].create(
            {
                "name": "Product A",
                "list_price": 100.0,
                "taxes_id": [(6, 0, [self.tax.id])],
            }
        )
        self.product_b = self.env["product.product"].create(
            {"name": "Product B", "list_price": 200.0}
        )

        # --- Pricelist (optional scenarios) ---
        # Use 'without_discount' so rules are shown in 'discount' when needed.
        self.pricelist = self.env["product.pricelist"].create(
            {
                "name": "PL Combined",
                "currency_id": self.env.company.currency_id.id,
                "discount_policy": "without_discount",
            }
        )
        # Fixed price rule for Product B (e.g., 150.0)
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.product_b.id,
                "fixed_price": 150.0,
            }
        )
        # Percentage discount rule for Product A (e.g., 20%)
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.product.id,
                "compute_price": "percentage",
                "percent_price": 20.0,
            }
        )

        # --- Order (default without pricelist, optional tests will set one) ---
        self.order = self.env["sale.order"].create({"partner_id": self.partner.id})

        # --- Initial order line (minimal path) ---
        self.line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "product_id": self.product.id,
                "name": self.product.name,
                "product_uom_qty": 1,
            }
        )

        # --- Groups / users for inverse behavior ---
        try:
            self.group_editor = self.env.ref(
                "falker_sale_price_control.group_price_editor"
            )
        except ValueError:
            self.group_editor = self.env["res.groups"].create(
                {"name": "Price Editor (Test)"}
            )

        base_group = self.env.ref("base.group_user")

        self.user_no_perm = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "No Perm",
                    "login": "no_perm_tester",
                    "email": "no_perm@test.example.com",
                    "groups_id": [(6, 0, [base_group.id])],
                }
            )
        )

        self.user_with_perm = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "With Perm",
                    "login": "with_perm_tester",
                    "email": "with_perm@test.example.com",
                    "groups_id": [(6, 0, [base_group.id, self.group_editor.id])],
                }
            )
        )

    # -------------------------
    # Helper
    # -------------------------
    def _recompute_line(self, line):
        """
        Force recompute of price-related fields to reflect pricelist rules.
        Useful in tests when timing/prefetch might skip automatic computes.
        """
        line._compute_pricelist_item_id()
        line._compute_price_unit()
        line._compute_discount()
        # fiscal_price mirrors price_unit automatically (compute).

    # -------------------------
    # Minimal: mirror invariants
    # -------------------------
    def test_mirror_on_create(self):
        """fiscal_price must mirror price_unit on create."""
        self.assertEqual(self.line.fiscal_price, self.line.price_unit)

    def test_mirror_after_price_change(self):
        """
        Directly changing price_unit should be mirrored by fiscal_price
        (compute handles the sync).
        """
        self.line.write({"price_unit": 123.45})
        self.assertAlmostEqual(self.line.fiscal_price, 123.45, places=2)

    def test_mirror_survives_taxes_change(self):
        """Changing taxes must not break the mirror relation."""
        self.line.write({"tax_id": [(6, 0, [self.tax.id])]})
        self.assertEqual(self.line.fiscal_price, self.line.price_unit)

    def test_note_line(self):
        """A note line has zero unit price and falsy fiscal_price."""
        note = self.env["sale.order.line"].create(
            {"order_id": self.order.id, "name": "Note", "display_type": "line_note"}
        )
        self.assertEqual(note.price_unit, 0.0)
        self.assertFalse(note.fiscal_price)

    def test_zero_quantity_does_not_break_mirror(self):
        """Setting quantity to zero keeps mirror intact."""
        self.line.write({"product_uom_qty": 0})
        self.assertEqual(self.line.fiscal_price, self.line.price_unit)

    def test_mirror_after_confirm(self):
        """Confirming the order must not break the mirror."""
        self.order.action_confirm()
        self.assertEqual(self.line.fiscal_price, self.line.price_unit)

    # -------------------------
    # Minimal: inverse behavior (group-gated)
    # -------------------------
    def test_inverse_with_permission(self):
        """
        Users in the editor group: writing fiscal_price updates price_unit.
        """
        line = self.line.with_user(self.user_with_perm)
        line.write({"fiscal_price": 111.11})
        self.assertAlmostEqual(line.price_unit, 111.11, places=2)
        self.assertAlmostEqual(line.fiscal_price, 111.11, places=2)

    def test_inverse_without_permission(self):
        """
        Users without the editor group: writing fiscal_price is ignored
        (fiscal_price mirrors price_unit).
        """
        orig = self.line.price_unit
        line = self.line.with_user(self.user_no_perm)
        line.write({"fiscal_price": 999.99})
        self.assertAlmostEqual(line.price_unit, orig, places=2)
        self.assertAlmostEqual(line.fiscal_price, orig, places=2)

    # -------------------------
    # Optional: pricelist interactions (mirror only)
    # -------------------------
    def test_create_with_pricelist_rules_mirror_holds(self):
        """
        Creating lines under a pricelist should keep the mirror invariant,
        regardless of how core sale represents price/discount.
        """
        order_pl = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": self.pricelist.id,
            }
        )
        line_a = self.env["sale.order.line"].create(
            {
                "order_id": order_pl.id,
                "product_id": self.product.id,
                "name": "A",
                "product_uom_qty": 1,
            }
        )
        self._recompute_line(line_a)
        self.assertEqual(line_a.fiscal_price, line_a.price_unit)

        line_b = self.env["sale.order.line"].create(
            {
                "order_id": order_pl.id,
                "product_id": self.product_b.id,
                "name": "B",
                "product_uom_qty": 2,
            }
        )
        self._recompute_line(line_b)
        self.assertEqual(line_b.fiscal_price, line_b.price_unit)

    def test_change_product_under_pricelist_mirror_holds(self):
        """
        Changing the product with a pricelist in place must keep the mirror
        invariant. No numeric assertions about core pricing logic.
        """
        order_pl = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": self.pricelist.id,
            }
        )
        line = self.env["sale.order.line"].create(
            {
                "order_id": order_pl.id,
                "product_id": self.product.id,
                "name": "Line",
                "product_uom_qty": 1,
            }
        )
        self._recompute_line(line)
        line.write({"product_id": self.product_b.id, "product_uom_qty": 3})
        self._recompute_line(line)
        self.assertEqual(line.fiscal_price, line.price_unit)
