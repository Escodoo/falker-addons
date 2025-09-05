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
        "crm",
    ],
    "data": [
        # Security
        "security/mautic_groups.xml",
        "security/ir.model.access.csv",
        # Data
        "data/mautic_cron.xml",
        # Views
        "views/res_company.xml",
        "views/res_partner.xml",
        "views/mautic_sync_log_views.xml",
        "views/mautic_segment_views.xml",
        "views/mautic_tag_views.xml",
        "views/mautic_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
}
