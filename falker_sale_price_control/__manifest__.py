{
    "name": "Sale Price Control",
    "version": "14.0.1.0.0",
    "summary": "Control for sale order line prices",
    "author": "Escodoo",
    "license": "AGPL-3",
    "website": "https://github.com/Escodoo/falker-addons",
    "depends": ["l10n_br_sale"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/sale_order_line_view.xml",
    ],
    "demo": [],
    "test": ["tests/test_sale_order_line.py"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
