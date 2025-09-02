# Copyright 2025 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Falker MRP Custom",
    "summary": """
        Falker MRP Custom""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "Escodoo",
    "website": "https://github.com/Escodoo/falker-addons",
    "depends": ["mrp"],
    "data": [
        "security/falker_security.xml",
        "security/ir.model.access.csv",
        "views/product_product.xml",
        "views/product_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "falker_mrp_custom/static/src/**/*",
        ],
    },
    "pre_init_hook": "pre_absorb_old_module",
}
