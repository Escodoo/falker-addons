# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class MauticSyncLog(models.Model):
    _name = "mautic.sync.log"
    _description = "Synchronization Log with Mautic"
    _order = "execution_time desc"

    name = fields.Char(readonly=True)

    sync_type = fields.Selection(
        [
            ("contact", "Contact"),
            ("company", "Company"),
            ("lead", "Lead"),
            ("segment", "Segment"),
            ("tag", "Tag"),
        ],
        required=True,
        readonly=True,
    )

    execution_time = fields.Datetime(
        string="Execution Date", default=fields.Datetime.now, readonly=True
    )
    total_processed = fields.Integer(readonly=True)
    success_count = fields.Integer(string="Successes", readonly=True)
    error_count = fields.Integer(string="Failures", readonly=True)
    log_detail = fields.Text(string="Details", readonly=True)
    state = fields.Selection(
        [
            ("done", "Done"),
            ("error", "Error"),
            ("partial", "Partial"),
        ],
        default="done",
        readonly=True,
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
