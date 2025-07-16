from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSaleOrderLinePriceControl(TransactionCase):
    def setUp(self):
        super().setUp()
        # Basic setup
        self.tax = self.env["account.tax"].create(
            {
                "name": "Tax 10%",
                "amount": 10.0,
                "type_tax_use": "sale",
            }
        )

        self.tax_icms = self.env["account.tax"].create(
            {
                "name": "ICMS Test",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 17.0,
            }
        )

        self.tax_ipi = self.env["account.tax"].create(
            {
                "name": "IPI Test",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 5.0,
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
                "taxes_id": [(6, 0, [self.tax_icms.id, self.tax_ipi.id])],
            }
        )

        self.discount_product = self.env["product.product"].create(
            {
                "name": "Discount Product",
                "list_price": 50.0,
                "taxes_id": [(6, 0, [self.tax_icms.id])],
            }
        )

        self.pricelist = self.env["product.pricelist"].create(
            {
                "name": "Test Pricelist",
                "currency_id": self.env.company.currency_id.id,
                "discount_policy": "without_discount",
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

        self.discount_pricelist_item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.discount_product.id,
                "compute_price": "percentage",
                "percent_price": 20.0,  # 20% discount
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
        self.order_line._compute_fiscal_price()
        self.assertEqual(
            self.order_line.fiscal_price,
            100.0,
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
            150.0,
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
        """Test tax recalculation when changing products"""
        test_product = self.env["product.product"].create(
            {
                "name": "Test Product for Tax Change",
                "list_price": 75.0,
                "taxes_id": [(6, 0, [self.tax.id])],
            }
        )

        self.order_line.write(
            {
                "product_id": test_product.id,
                "product_uom_qty": 1,
            }
        )
        self.order_line.product_id_change()

        self.assertEqual(
            self.order_line.price_unit,
            75.0,
            "Price should be updated to the product's list price",
        )
        self.assertEqual(
            self.order_line.tax_id,
            self.tax,
            "Taxes should be updated to the product's taxes",
        )
        self.assertEqual(
            self.order_line.fiscal_price,
            75.0,
            "Fiscal price should follow the unit price",
        )

    def test_empty_order_line(self):
        """Test a line without fiscal_price."""
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

    def test_multiple_taxes_impact(self):
        """Verify fiscal price with multiple taxes"""
        new_line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "product_id": self.new_product.id,
                "name": self.new_product.name,
                "product_uom_qty": 1,
                "fiscal_tax_ids": [(6, 0, [self.tax_icms.id, self.tax_ipi.id])],
            }
        )

        self.assertEqual(
            new_line.fiscal_price,
            150.0,
            "Fiscal price should be equal to unit price regardless of multiple taxes",
        )

    def test_pricelist_discount_application(self):
        """Test fiscal price with pricelist percentage discount"""
        discount_line = self.env["sale.order.line"].create(
            {
                "order_id": self.order.id,
                "product_id": self.discount_product.id,
                "name": self.discount_product.name,
                "product_uom_qty": 2,
            }
        )

        expected_price = 50.0 * 0.8  # 20% discount from pricelist
        self.assertEqual(
            discount_line.price_unit,
            expected_price,
            "Price should respect the percentage discount from pricelist",
        )
        self.assertEqual(
            discount_line.fiscal_price,
            expected_price,
            "Fiscal price should follow the discounted price",
        )

    def test_zero_quantity_line(self):
        """Test behavior when quantity is zero"""
        self.order_line.write({"product_uom_qty": 0})
        self.order_line._compute_fiscal_price()

        self.assertEqual(
            self.order_line.fiscal_price,
            100.0,
            "Fiscal price should remain unchanged even with zero quantity",
        )

    def test_fiscal_price_after_order_confirmation(self):
        """Verify fiscal price persists after order confirmation"""
        self.order.action_confirm()
        self.assertEqual(
            self.order_line.fiscal_price,
            100.0,
            "Fiscal price should remain after order confirmation",
        )
