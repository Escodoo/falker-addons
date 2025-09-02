/** @odoo-module **/

import {BomOverviewComponent} from "@mrp/components/bom_overview/mrp_bom_overview";
import {patch} from "@web/core/utils/patch";

patch(BomOverviewComponent.prototype, "falker_mrp_custom.BomOverviewComponent", {
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
                this.state.showOptions.costs = hasGroup;
            } else {
                this.state.showOptions.costs = false;
            }
        } catch (error) {
            this.state.showOptions.costs = false;
        }
    },

    onChangeDisplay(displayInfo) {
        if (displayInfo === "costs" && this.state.showOptions.costs === false) {
            return;
        }
        return this._super(...arguments);
    },
});
