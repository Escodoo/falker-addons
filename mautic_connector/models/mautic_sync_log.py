# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class MauticSyncLog(models.Model):
    _name = "mautic.sync.log"
    _description = "Synchronization Log with Mautic"
    _order = "execution_time desc"

    name = fields.Char()

    sync_type = fields.Selection(
        [
            ("contact", "Contact"),
            ("company", "Company"),
            ("lead", "Lead"),
        ],
        required=True,
    )

    execution_time = fields.Datetime(
        string="Execution Date", default=fields.Datetime.now
    )
    total_processed = fields.Integer(string="Total Processed")
    success_count = fields.Integer(string="Successes")
    error_count = fields.Integer(string="Failures")
    log_detail = fields.Text(string="Details")
    state = fields.Selection(
        [
            ("done", "Done"),
            ("error", "Error"),
            ("partial", "Partial"),
        ],
        default="done",
    )

    @api.depends("sync_type", "execution_time", "success_count", "error_count")
    def name_get(self):
        result = []
        for record in self:
            exec_date = (
                record.execution_time.strftime("%Y-%m-%d %H:%M")
                if record.execution_time
                else ""
            )
            sync_label = dict(self._fields["sync_type"].selection).get(
                record.sync_type, ""
            )
            display_name = f"[{exec_date}] {sync_label}"
            result.append((record.id, display_name))
        return result
