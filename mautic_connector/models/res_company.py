# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import requests

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

    def refresh_token(self):
        token_url = f"{self.mautic_api_url}/oauth/v2/token"
        payload = {
            "client_id": self.mautic_client_id,
            "client_secret": self.mautic_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.mautic_refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Odoo/Mautic OAuth",
        }

        try:
            res = requests.post(token_url, headers=headers, data=payload, timeout=30)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            raise ValidationError(_("Error renewing token: %s") % e) from e

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            raise ValidationError(_("No access token received from Mautic."))
        self.write(
            {
                "mautic_access_token": access_token,
                "mautic_refresh_token": refresh_token or self.mautic_refresh_token,
            }
        )

        return _("Token updated successfully!")
