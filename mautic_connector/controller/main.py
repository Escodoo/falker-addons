# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import requests

from odoo import http


class MauticController(http.Controller):
    @http.route("/get_auth_code", type="http", auth="public", website=True)
    def get_auth_code(self, **kwarg):
        comp = http.request.env["res.users"].sudo().search([], limit=1).company_id

        if "code" not in kwarg:
            return "Code not received from Mautic."

        code = kwarg["code"]

        token_url = f"{comp.mautic_api_url}/oauth/v2/token"
        redirect_uri = comp.mautic_request_token_url

        payload = {
            "client_id": comp.mautic_client_id,
            "client_secret": comp.mautic_client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
            "grant_type": "authorization_code",
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        res = requests.post(token_url, headers=headers, data=payload, timeout=30)
        res.raise_for_status()

        parsed_response = res.json()
        access_token = parsed_response.get("access_token")

        if not access_token:
            return "Token not received. See the logs."

        comp.write(
            {
                "mautic_access_token": access_token,
                "mautic_auth_code": code,
                "mautic_client_id": comp.mautic_client_id,
                "mautic_client_secret": comp.mautic_client_secret,
                "mautic_request_token_url": redirect_uri,
            }
        )

        return "Successfully connected, please close this window."
