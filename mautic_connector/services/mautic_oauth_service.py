# Copyright 2025 - TODAY, Cristiano Mafra Junior
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import requests
import logging
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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
            return self._refresh_token(company)

        return company.mautic_access_token

    def _refresh_token(self, company, refresh_token_from_db=None):
        refresh_token = refresh_token_from_db or company.mautic_refresh_token

        if not refresh_token:
            raise ValidationError(_("Mautic refresh token não configurado."))

        payload = {
            "grant_type": "refresh_token",
            "client_id": company.mautic_client_id,
            "client_secret": company.mautic_client_secret,
            "refresh_token": refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Odoo/Mautic OAuth",
        }

        url = f"{company.mautic_api_url.rstrip('/')}/oauth/v2/token"

        response = requests.post(url, headers=headers, data=payload, timeout=30)

        if response.status_code != 200:
            raise ValidationError(
                f"Erro ao renovar token do Mautic: {response.text}"
            )

        data = response.json()

        expires_at = None
        if data.get("expires_in"):
            expires_at = fields.Datetime.now() + relativedelta(
                seconds=data["expires_in"]
            )

        new_access_token = data["access_token"]
        new_refresh_token = data.get("refresh_token") or refresh_token

        # 🔥 Transação isolada
        new_cr = self.env.registry.cursor()
        try:
            new_cr.execute(
                """
                UPDATE res_company
                   SET mautic_access_token     = %s,
                       mautic_refresh_token    = %s,
                       mautic_token_expires_at = %s
                 WHERE id = %s
                """,
                [
                    new_access_token,
                    new_refresh_token,
                    expires_at,
                    company.id,
                ],
            )
            new_cr.commit()

            _logger.info(
                "[Mautic] Token salvo em transação independente. "
                "Company %s, expira em %s",
                company.id,
                expires_at,
            )
        except Exception:
            new_cr.rollback()
            _logger.exception("[Mautic] Falha ao salvar token.")
            raise
        finally:
            new_cr.close()

        # 🔥 limpa cache do ORM
        self.env.invalidate_all()

        return new_access_token