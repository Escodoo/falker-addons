/** @odoo-module **/

import {BomOverviewDisplayFilter} from "@mrp/components/bom_overview_display_filter/mrp_bom_overview_display_filter";
import {patch} from "@web/core/utils/patch";

patch(
    BomOverviewDisplayFilter.prototype,
    "falker_mrp_custom.BomOverviewDisplayFilter",
    {
        setup() {
            this._super(...arguments);
            this._checkCostGroupPermissionPromise = this._checkCostGroupPermission();
        },

        async _checkCostGroupPermission() {
            try {
                const userService = this.env.services.user;

                if (userService) {
                    const hasGroup = await userService.hasGroup(
                        "falker_mrp_custom.group_falker_cost_info"
                    );
                    this.userHasCostGroup = hasGroup;
                } else {
                    this.userHasCostGroup = false;
                }
            } catch (error) {
                this.userHasCostGroup = false;
            }
        },

        get displayableOptions() {
            const originalOptions = this._super(...arguments);

            if (this.userHasCostGroup === false) {
                return originalOptions.filter((option) => option !== "costs");
            }

            return originalOptions;
        },
    }
);
