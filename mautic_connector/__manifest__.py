{
    "name": "Odoo Mautic Connector",
    "version": "16.0.1.0.0",
    "sumarry": "Mautic Connector",
    "category": "Construction",
    "author": "Escodoo, Odoo Community Association (OCA)",
    "website": "https://github.com/Escodoo/falker-addons",
    "license": "AGPL-3",
    "depends": [
        "account",
        "sale",
        "sale_management",
        "account_asset_management",
        "crm",
    ],
    "data": [
        # Security
        "security/ir.model.access.csv",
        # Data
        "data/mautic_cron.xml",
        "data/crm_tag_falker.xml",
        # Views
        "views/res_company.xml",
        "views/res_partner.xml",
        "views/mautic_sync_log_views.xml",
    ],
    "installable": True,
    "auto_install": False,
}
