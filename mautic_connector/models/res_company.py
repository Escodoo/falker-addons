# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"
    mautic_company_id = fields.Char("mautic_company_id")
    mautic_id = fields.Char("ID")
    mautic_exported = fields.Boolean("x_is_exported", default=False)
    mautic_is_updated = fields.Boolean("mautic_is_updated", default=False)
    mautic_client_id = fields.Char("Client ID")
    mautic_client_secret = fields.Char("Client Secret")
    mautic_auth_base_url = fields.Char("Authorization URL")
    mautic_api_url = fields.Char(string="URL da API")

    mautic_request_token_url = fields.Char(
        "Redirect URL",
        default="https://localhost:8011/get_auth_code ",
    )
    mautic_auth_code = fields.Char("Auth Code")
    mautic_access_token = fields.Char("Access Token")

    def authenticate(self):
        try:
            url = (
                f"{self.mautic_auth_base_url}"
                f"?client_id={self.mautic_client_id}"
                f"&redirect_uri={self.mautic_request_token_url}"
                f"&response_type=code"
            )
            return {"type": "ir.actions.act_url", "url": url, "target": "new"}
        except Exception:
            raise ValidationError(_("Fill up the correct information...!!"))

    def refresh_token(self):
        try:
            url = (
                self.mautic_auth_base_url
                + "?client_id="
                + self.mautic_client_id
                + "&redirect_uri="
                + self.mautic_request_token_url
                + "&response_type=code&grant_type=refresh_token&code=UNIQUE_CODE_STRING"
            )
            return {"type": "ir.actions.act_url", "url": url, "target": "new"}
        except Exception:
            raise ValidationError(_("Fill up the correct information...!!"))

    def import_contacts(self):
        headers = {
            "Authorization": f"Bearer {self.mautic_access_token}",
            "content-type": "application/json",
        }

        total = 0
        success = 0
        errors = 0
        messages = []

        try:
            res = requests.get(
                f"{self.mautic_api_url}/api/contacts?limit=6500",
                headers=headers,
                timeout=30,
            )
            res.raise_for_status()
            result = res.json()

            for __, val in result.get("contacts", {}).items():
                total += 1
                try:
                    my_dict = {}

                    firstname = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("firstname", {})
                        .get("value")
                        or ""
                    )
                    lastname = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("lastname", {})
                        .get("value")
                        or ""
                    )
                    if not firstname and not lastname:
                        continue

                    my_dict["name"] = f"{firstname} {lastname}".strip()
                    my_dict["mautic_id"] = val.get("id")

                    my_dict["street2"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("address2", {})
                        .get("value")
                    )
                    my_dict["street"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("address1", {})
                        .get("value")
                    )
                    my_dict["mobile"] = val.get("fields", {}).get("core", {}).get(
                        "mobile", {}
                    ).get("value") or val.get("mobile")
                    my_dict["phone"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("phone", {})
                        .get("value")
                    )
                    my_dict["email"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("email", {})
                        .get("value")
                    )
                    my_dict["zip"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("zipcode", {})
                        .get("value")
                    )
                    my_dict["city"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("city", {})
                        .get("value")
                    )
                    my_dict["website"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("website", {})
                        .get("value")
                    )
                    my_dict["function"] = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("position", {})
                        .get("value")
                    )

                    country_name = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("country", {})
                        .get("value")
                    )
                    if country_name:
                        country_id = (
                            self.env["res.country"]
                            .with_context(lang="en_US")
                            .search([("name", "=", country_name)], limit=1)
                        )
                        if country_id:
                            my_dict["country_id"] = country_id.id

                    state_name = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("state", {})
                        .get("value")
                    )
                    if state_name:
                        state_id = self.env["res.country.state"].search(
                            [("name", "=", state_name)], limit=1
                        )
                        if state_id:
                            my_dict["state_id"] = state_id.id

                    partner_name = (
                        val.get("fields", {})
                        .get("core", {})
                        .get("company", {})
                        .get("value")
                    )
                    if partner_name:
                        partner = self.env["res.partner"].search(
                            [("name", "=", partner_name)], limit=1
                        )
                        if partner:
                            my_dict["parent_id"] = partner.id

                    res_partner = self.env["res.partner"].search(
                        [("mautic_id", "=", val.get("id"))], limit=1
                    )

                    if not res_partner:
                        self.env["res.partner"].create(my_dict)
                    else:
                        res_partner.write(my_dict)

                    success += 1

                except Exception as e:
                    errors += 1
                    msg = f"Erro ao processar contato ID {val.get('id')}: {str(e)}"
                    messages.append(msg)
                    _logger.error(msg)

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "contact",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total,
                    "success_count": success,
                    "error_count": errors,
                    "log_detail": "\n".join(messages),
                    "state": "done" if errors == 0 else "partial",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Importação concluída"),
                    "message": _("Total: %s | Sucesso: %s") % (total, success),
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error(f"Erro ao acessar API do Mautic: {str(e)}")
            raise UserError(
                _("Erro ao buscar dados de contatos do Mautic. Verifique os logs.")
            )

        except Exception:
            _logger.exception("Erro inesperado ao importar contatos.")
            raise UserError(
                _("Erro inesperado ao importar contatos. Verifique os logs.")
            )

    def import_company(self):
        headers = {
            "Authorization": f"Bearer {self.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = 0
        success = 0
        errors = 0
        messages = []
        try:
            res = requests.get(
                f"{self.mautic_api_url}/api/companies?limit=200",
                headers=headers,
                timeout=30,
            )
            res.raise_for_status()
            companies = res.json().get("companies", {})

            for __, val in companies.items():
                total += 1
                try:
                    fields_all = val.get("fields", {}).get("all", {})
                    fields_core = val.get("fields", {}).get("core", {})

                    data_dict = {
                        "mautic_company_id": val.get("id"),
                        "website": fields_all.get("companywebsite"),
                        "zip": fields_all.get("companyzipcode"),
                        "city": fields_all.get("companycity"),
                        "street": fields_all.get("companyaddress1"),
                        "street2": fields_all.get("companyaddress2"),
                        "email": fields_core.get("companyemail", {}).get("value"),
                        "name": fields_core.get("companyname", {}).get("value"),
                        "is_company": True,
                    }

                    country_name = fields_all.get("companycountry")
                    if country_name:
                        country = (
                            self.env["res.country"]
                            .with_context(lang="en_US")
                            .search([("name", "=", country_name)], limit=1)
                        )
                        if country:
                            data_dict["country_id"] = country.id

                    state_name = fields_all.get("companystate")
                    if state_name:
                        state = self.env["res.country.state"].search(
                            [("name", "=", state_name)], limit=1
                        )
                        if state:
                            data_dict["state_id"] = state.id

                    email = data_dict.get("email")
                    name = data_dict.get("name")

                    existing = self.env["res.partner"].search(
                        [
                            ("email", "=", email),
                            ("name", "=", name),
                        ],
                        limit=1,
                    )

                    company = self.env["res.partner"].search(
                        [("mautic_company_id", "=", val.get("id"))], limit=1
                    )

                    if company or existing:
                        (company or existing).write(data_dict)
                    else:
                        self.env["res.partner"].create(data_dict)

                    success += 1

                except Exception as e:
                    errors += 1
                    msg = f"Erro ao processar empresa ID {val.get('id')}: {str(e)}"
                    messages.append(msg)
                    _logger.error(msg)

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "company",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total,
                    "success_count": success,
                    "error_count": errors,
                    "log_detail": "\n".join(messages),
                    "state": "done" if errors == 0 else "partial",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Importação concluída"),
                    "message": _("Total: %s | Sucesso: %s") % (total, success),
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error(f"Erro ao acessar API do Mautic: {str(e)}")
            raise UserError(
                _("Erro ao buscar dados de empresas do Mautic. Verifique os logs.")
            )

        except Exception:
            _logger.exception("Erro inesperado ao importar empresas.")
            raise UserError(
                _("Erro inesperado ao importar empresas. Verifique os logs.")
            )
