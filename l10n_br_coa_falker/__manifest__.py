# Copyright 2024 - TODAY, Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Falker - Plano de Contas",
    "version": "14.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "author": "Escodoo, Odoo Community Association (OCA)",
    "website": "https://github.com/Escodoo/falker-addons",
    "depends": ["l10n_br_coa"],
    "data": [
        "data/falker_coa_template.xml",
        "data/account_group.xml",
        "data/account.account.template.csv",
        "data/account_fiscal_position_template.xml",
        "data/falker_coa_template_post.xml",
    ],
    "post_init_hook": "post_init_hook",
}
