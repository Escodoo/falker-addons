# Copyright 2025 - TODAY, Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import requests
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class MauticOAuthService(models.AbstractModel):
    _name = "mautic.oauth.service"
    _description = "Mautic OAuth Service"

    def get_valid_access_token(self, company, force_refresh=False):
        self.env.cr.execute(
            """
            SELECT id
            FROM res_company
            WHERE id = %s
            FOR UPDATE
            """,
            [company.id],
        )

        now = fields.Datetime.now()

        must_refresh = (
            force_refresh
            or not company.mautic_access_token
            or not company.mautic_token_expires_at
            or company.mautic_token_expires_at <= now
        )

        if must_refresh:
            self._refresh_token(company)

        return company.mautic_access_token

    def _refresh_token(self, company):
        if not company.mautic_refresh_token:
            raise ValidationError(_("Mautic refresh token não configurado."))

        payload = {
            "grant_type": "refresh_token",
            "client_id": company.mautic_client_id,
            "client_secret": company.mautic_client_secret,
            "refresh_token": company.mautic_refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Odoo/Mautic OAuth",
        }

        url = f"{company.mautic_api_url.rstrip('/')}/oauth/v2/token"

        response = requests.post(url, headers=headers, data=payload, timeout=30)
        if response.status_code != 200:
            raise ValidationError(f"Erro ao renovar token do Mautic: {response.text}")
        data = response.json()
        values = {
            "mautic_access_token": data["access_token"],
        }
        if data.get("refresh_token"):
            values["mautic_refresh_token"] = data["refresh_token"]
        if data.get("expires_in"):
            values["mautic_token_expires_at"] = fields.Datetime.now() + relativedelta(
                seconds=data["expires_in"]
            )
        company.sudo().write(values)
