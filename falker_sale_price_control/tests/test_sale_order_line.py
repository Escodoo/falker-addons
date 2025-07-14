from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSaleOrderLinePriceControl(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tax_icms = self.env["account.tax"].create(
            {
                "name": "ICMS Test",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 17.0,
            }
        )

        self.product = self.env["product.product"].create(
            {
                "name": "Test Product",
                "list_price": 100.0,
                "taxes_id": [(6, 0, [self.tax_icms.id])],
            }
        )

        self.new_product = self.env["product.product"].create(
            {
                "name": "New Test Product",
                "list_price": 200.0,
                "taxes_id": [(6, 0, [self.tax_icms.id])],
            }
        )

        self.pricelist = self.env["product.pricelist"].create(
            {
                "name": "Test Pricelist",
                "currency_id": self.env.company.currency_id.id,
            }
        )

        self.pricelist_item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.new_product.id,
                "fixed_price": 150.0,
            }
        )

        self.order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"]
                .create({"name": "Test Partner"})
                .id,
                "pricelist_id": self.pricelist.id,
            }
        )

        self.order_line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "product_id": self.product.id,
                "name": self.product.name,
                "product_uom_qty": 1,
                "fiscal_tax_ids": [(6, 0, [self.tax_icms.id])],
            }
        )

    def test_fiscal_price_calculation(self):
        """Verifies the basic calculation of the fiscal price"""
        self.order_line._compute_fiscal_price()
        self.assertEqual(
            self.order_line.fiscal_price,
            self.order_line.price_unit,
            "The fiscal price must be equal to the unit price without adjustments.",
        )

    def test_fiscal_price_with_taxes(self):
        """Verifies the calculation with taxes applied"""
        # Force recalculation with taxes
        self.order_line._compute_fiscal_price()
        self.assertEqual(
            self.order_line.fiscal_price,
            100.0,  # Base price without tax adjustment
            "The fiscal price should remain as the base price even with taxes.",
        )

    def test_price_update_on_product_change(self):
        """Verifies price update when the product is changed"""

        self.order_line.write(
            {
                "product_id": self.new_product.id,
                "product_uom_qty": 2,
            }
        )

        self.assertEqual(
            self.order_line.price_unit,
            150.0,  # Price from price list
            "The price should be updated according to the pricelist when changing the product.",
        )

        self.assertEqual(
            self.order_line.fiscal_price,
            150.0,
            "The fiscal price should follow the change in unit price.",
        )

    def test_pricelist_price_application(self):
        """Verifies correct price application from the pricelist"""
        new_line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "product_id": self.new_product.id,
                "name": self.new_product.name,
                "product_uom_qty": 1,
            }
        )

        self.assertEqual(
            new_line.price_unit,
            150.0,
            "New products should have their price set according to the pricelist.",
        )

    def test_tax_recalculation_on_product_change(self):
        """Verifies if taxes are recalculated when the product is changed"""
        self.order_line.product_id = self.new_product
        self.order_line._onchange_product_id_custom_price()

        self.assertTrue(
            self.order_line.fiscal_tax_ids,
            "Fiscal taxes should be updated when the product is changed.",
        )

        self.assertEqual(
            len(self.order_line.fiscal_tax_ids),
            1,
            "It should retain only the configured taxes.",
        )

    def test_empty_order_line(self):
        """Testa uma linha vazia sem fiscal_price."""
        empty_line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "name": "Empty Line",
                "display_type": "line_note",
            }
        )
        self.assertEqual(
            empty_line.price_unit, 0.0, "Empty line should have zero price"
        )
        self.assertFalse(
            empty_line.fiscal_price, "Empty line should have no fiscal price"
        )
