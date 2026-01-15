# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo import _, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"
    mautic_client_id = fields.Char(string="Client ID")
    mautic_client_secret = fields.Char(string="Client Secret")
    mautic_auth_base_url = fields.Char(string="Authorization URL")
    mautic_api_url = fields.Char(string="URL da API")

    mautic_request_token_url = fields.Char(
        string="Redirect URL",
        default="https://localhost:8011/get_auth_code ",
    )
    mautic_auth_code = fields.Char("Auth Code")
    mautic_access_token = fields.Char("Access Token")
    mautic_refresh_token = fields.Char("Refresh Token")
    mautic_token_expires_at = fields.Datetime("Token expires at")

    def authenticate(self):
        try:
            url = (
                f"{self.mautic_auth_base_url}"
                f"?client_id={self.mautic_client_id}"
                f"&redirect_uri={self.mautic_request_token_url}"
                f"&response_type=code"
            )
            return {"type": "ir.actions.act_url", "url": url, "target": "new"}
        except Exception as err:
            raise ValidationError(_("Fill up the correct information...!!")) from err

    def is_mautic_token_expired(self):
        self.ensure_one()
        if not self.mautic_access_token or not self.mautic_token_expires_at:
            return True
        return fields.Datetime.now() >= self.mautic_token_expires_at

    def refresh_token(self):
        self.ensure_one()
        service = self.env["mautic.oauth.service"]
        return service.get_valid_access_token(self)
