# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class MauticSyncLog(models.Model):
    _name = "mautic.sync.log"
    _description = "Synchronization Log with Mautic"
    _order = "execution_time desc"

    sync_type = fields.Selection(
        [
            ("contact", "Contact"),
            ("company", "Company"),
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
