# Copyright 2025 - TODAY, Kaynnan Lemes <kaynnan.lemes@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from openupgradelib import openupgrade


def pre_absorb_old_module(cr):
    if openupgrade.is_module_installed(
        cr, "falker_mrp_production_byproduct_cost_share_custom"
    ):
        openupgrade.update_module_names(
            cr,
            [
                (
                    "falker_mrp_production_byproduct_cost_share_custom",
                    "falker_mrp_custom",
                ),
            ],
            merge_modules=True,
        )
