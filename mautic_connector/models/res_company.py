# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import unicodedata

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def _norm(text):
    if not text:
        return ""
    return (
        "".join(
            c
            for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )
        .lower()
        .strip()
    )


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

    def _norm(self, s):
        if not s:
            return ""
        return (
            "".join(
                c
                for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c)
            )
            .strip()
            .lower()
        )

    def _find_state(self, value, country=None):
        """
        Busca estado/província por código (SP/CA/BC) ou nome (com/sem acento).
        `country` pode ser record, id numérico, código ISO2 ou nome.
        Se não resolver país, faz fallback global (menos preciso).
        """
        State = self.env["res.country.state"]
        Country = self.env["res.country"]

        if not value:
            return State

        val = str(value).strip()
        domain = []

        if country:
            cid = getattr(country, "id", None)
            if not cid:
                s = str(country).strip()
                if s.isdigit():
                    cid = int(s)
                else:
                    c = Country.search(
                        ["|", ("code", "=", s.upper()), ("name", "=", s)], limit=1
                    )
                    if not c:
                        target = self._norm(s)
                        for cand in Country.search([]):
                            if self._norm(cand.name) == target:
                                c = cand
                                break
                    cid = c.id if c else False
            if cid:
                domain = [("country_id", "=", cid)]

        st = State.search(domain + [("code", "=", val.upper())], limit=1)
        if st:
            return st
        st = State.search(domain + [("name", "=", val)], limit=1)
        if st:
            return st
        target = self._norm(val)
        candidates = State.search(domain or []) or State.search([])
        for s in candidates:
            if self._norm(s.name) == target:
                return s

        return State

    def import_contacts(self):  # noqa: C901
        headers = {
            "Authorization": f"Bearer {self.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, updated, skipped = [], [], [], []

        try:
            res = requests.get(
                f"{self.mautic_api_url}/api/contacts?limit=6500",
                headers=headers,
                timeout=30,
            )
            res.raise_for_status()
            result = res.json()

            Partner = self.env["res.partner"].sudo()
            for __, val in (result.get("contacts", {}) or {}).items():
                total += 1
                try:
                    core = (val.get("fields") or {}).get("core", {}) or {}
                    firstname = (core.get("firstname") or {}).get("value") or ""
                    lastname = (core.get("lastname") or {}).get("value") or ""
                    full_name = f"{firstname} {lastname}".strip()
                    if not full_name:
                        continue
                    email = (core.get("email") or {}).get("value") or ""
                    full_name_norm = self._norm(full_name)
                    existing = Partner.search(
                        [("mautic_id", "=", val.get("id"))], limit=1
                    )
                    if not existing and email:
                        existing = Partner.search([("email", "=", email)], limit=1)
                    existing_name = None
                    if not existing:
                        existing_name = Partner.search(
                            [("name", "=", full_name), ("company_type", "=", "person")],
                            limit=1,
                        )
                        if not existing_name:
                            candidates = Partner.search(
                                [
                                    ("company_type", "=", "person"),
                                    ("name", "ilike", full_name),
                                ]
                            )
                            for p in candidates:
                                if self._norm(p.name) == full_name_norm:
                                    existing_name = p
                                    break
                    if existing_name and not existing:
                        skipped.append(full_name)
                        continue
                    my_dict = {
                        "name": full_name,
                        "mautic_id": val.get("id"),
                        "street": (core.get("address1") or {}).get("value") or "",
                        "street2": (core.get("address2") or {}).get("value") or "",
                        "mobile": (core.get("mobile") or {}).get("value")
                        or (val.get("mobile") or ""),
                        "phone": (core.get("phone") or {}).get("value") or "",
                        "email": email,
                        "zip": (core.get("zipcode") or {}).get("value") or "",
                        "city": (core.get("city") or {}).get("value") or "",
                        "website": (core.get("website") or {}).get("value") or "",
                        "function": (core.get("position") or {}).get("value") or "",
                        "company_type": "person",
                    }

                    country_name = (core.get("country") or {}).get("value")
                    if country_name:
                        country_id = (
                            self.env["res.country"]
                            .with_context(lang="en_US")
                            .search([("name", "=", country_name)], limit=1)
                        )
                        if country_id:
                            my_dict["country_id"] = country_id.id

                    state_name = (core.get("state") or {}).get("value")
                    if state_name:
                        state_id = self.env["res.country.state"].search(
                            [("name", "=", state_name)], limit=1
                        )
                        if state_id:
                            my_dict["state_id"] = state_id.id
                    partner_name = (core.get("company") or {}).get("value")
                    if partner_name:
                        company = Partner.search(
                            [("is_company", "=", True), ("name", "=", partner_name)],
                            limit=1,
                        )
                        if company:
                            my_dict["parent_id"] = company.id
                    if not existing:
                        Partner.create(my_dict)
                        created.append(full_name)
                    else:
                        existing.write(my_dict)
                        updated.append(full_name)

                    success += 1

                except Exception as e:
                    errors += 1
                    messages.append(
                        f"Error processing contact ID {val.get('id')}: {str(e)}"
                    )
                    _logger.error(messages[-1])

            log_detail = (
                f"Created: {len(created)} ({', '.join(created)})\n"
                f"Updated: {len(updated)} ({', '.join(updated)})\n"
                f"Skipped (same name): {len(skipped)} ({', '.join(skipped)})\n"
                f"Errors: {errors}\n" + "\n".join(messages)
            )

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "contact",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total,
                    "success_count": success,
                    "error_count": errors,
                    "log_detail": log_detail,
                    "state": "done" if errors == 0 else "partial",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Importação concluída"),
                    "message": _(
                        "Total: %s | Criadas: %s | Atualizadas: %s | Ignoradas (nome): %s"
                    )
                    % (total, len(created), len(updated), len(skipped)),
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error(f"Error accessing Mautic contacts API: {str(e)}")
            raise UserError(_("Error fetching contact data from Mautic. Check logs."))

        except Exception:
            _logger.exception("Unexpected error importing contacts.")
            raise UserError(_("Unexpected error importing contacts. Check logs."))

    def import_company(self):  # noqa: C901

        headers = {
            "Authorization": f"Bearer {self.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, skipped = [], [], []

        try:
            limit, start = 100, 0
            while True:
                res = requests.get(
                    f"{self.mautic_api_url}/api/companies?limit={limit}&start={start}",
                    headers=headers,
                    timeout=30,
                )
                res.raise_for_status()
                companies = res.json().get("companies", {})
                if not companies:
                    break

                for __, val in companies.items():
                    total += 1
                    try:
                        fields_all = (val.get("fields") or {}).get("all", {}) or {}
                        fields_core = (val.get("fields") or {}).get("core", {}) or {}

                        name = (fields_core.get("companyname", {}) or {}).get(
                            "value"
                        ) or ""
                        email = (fields_core.get("companyemail", {}) or {}).get(
                            "value"
                        ) or ""
                        name_norm = self._norm(name)

                        Partner = self.env["res.partner"].sudo()
                        existing = Partner.search(
                            [("mautic_company_id", "=", val.get("id"))], limit=1
                        )
                        # TODO: Pode ter parceiro diferente com mesmo e-mail
                        # if not existing and email:
                        #     existing = Partner.search(
                        #         [("email", "=", email), ("is_company", "=", True)],
                        #         limit=1,
                        #     )
                        if not existing and name:
                            existing = Partner.search(
                                [("is_company", "=", True), ("name", "=", name)],
                                limit=1,
                            )
                            if not existing:
                                candidates = Partner.search(
                                    [("is_company", "=", True), ("name", "ilike", name)]
                                )
                                for p in candidates:
                                    if self._norm(p.name) == name_norm:
                                        existing = p
                                        break
                        if existing:
                            skipped.append(name or f"ID {val.get('id')}")
                            continue

                        data_dict = {
                            "mautic_company_id": val.get("id"),
                            "website": fields_all.get("companywebsite") or "",
                            "zip": fields_all.get("companyzipcode") or "",
                            "city": fields_all.get("companycity") or "",
                            "street": fields_all.get("companyaddress1") or "",
                            "street2": fields_all.get("companyaddress2") or "",
                            "email": email,
                            "name": name,
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
                            state = self._find_state(state_name, country_name)
                            if state:
                                data_dict["state_id"] = state.id

                        self.env["res.partner"].create(data_dict)
                        created.append(name or f"ID {val.get('id')}")
                        success += 1

                    except Exception as e:
                        errors += 1
                        msg = f"Error processing company ID {val.get('id')} ({name}): {str(e)}"
                        messages.append(msg)

                start += limit

            log_detail = (
                f"Created: {len(created)} ({', '.join(created)})\n"
                f"Skipped: {len(skipped)} ({', '.join(skipped)})\n"
                f"Errors: {errors}\n" + "\n".join(messages)
            )

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "company",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total,
                    "success_count": success,
                    "error_count": errors,
                    "log_detail": log_detail,
                    "state": "done" if errors == 0 else "partial",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Importação concluída"),
                    "message": _("Total: %s | Criadas: %s | Ignoradas: %s")
                    % (total, len(created), len(skipped)),
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error(f"Erro ao acessar API do Mautic: {str(e)}")
            raise UserError(_("Error fetching company data from Mautic. Check logs."))

        except Exception:
            _logger.exception("Unexpected error importing companies.")
            raise UserError(_("Unexpected error importing companies. Check logs."))

    def import_leads(self):  # noqa: C901
        headers = {
            "Authorization": f"Bearer {self.mautic_access_token}",
            "Content-Type": "application/json",
        }

        total = success = errors = 0
        created, updated, messages = [], [], []
        skipped_no_email = 0

        Partner = self.env["res.partner"].sudo()
        Lead = self.env["crm.lead"].sudo()
        lead_has_mautic_id = "mautic_id" in Lead._fields

        try:
            res = requests.get(
                f"{self.mautic_api_url}/api/contacts?limit=6500",
                headers=headers,
                timeout=30,
            )
            res.raise_for_status()
            result = res.json() or {}

            for __, val in (result.get("contacts") or {}).items():
                total += 1
                try:
                    core = (val.get("fields") or {}).get("core", {}) or {}
                    firstname = (core.get("firstname") or {}).get("value") or ""
                    lastname = (core.get("lastname") or {}).get("value") or ""
                    full_name = f"{firstname} {lastname}".strip()
                    name_partner = (core.get("name") or {}).get("value") or ""
                    email = (core.get("email") or {}).get("value") or ""
                    country_name = (core.get("country") or {}).get("value") or ""
                    state_name = (core.get("state") or {}).get("value") or ""
                    city = (core.get("city") or {}).get("value") or ""
                    company_name = (core.get("company_name") or {}).get("value") or ""
                    personal_phone = (core.get("personal_phone") or {}).get(
                        "value"
                    ) or ""
                    cf_cargo_lead_sm = (core.get("cf_cargo_lead_sm") or {}).get(
                        "value"
                    ) or ""
                    cf_url_do_site = (core.get("cf_url_do_site") or {}).get(
                        "value"
                    ) or ""
                    # TODO: Vê Futuramente questão dos Marcadores
                    # cf_cultura_sm_pt = (core.get("cf_cultura_sm_pt") or {}).get("value") or ""
                    # cf_area_sm_pt = (core.get("cf_area_sm_pt") or {}).get("value") or ""
                    cf_informacoes_adicionais = (
                        core.get("cf_informacoes_adicionais") or {}
                    ).get("value") or ""

                    if full_name:
                        continue

                    if not email:
                        skipped_no_email += 1
                        continue

                    partner = Partner.search([("email", "=ilike", email)], limit=1)
                    if not partner:
                        partner_vals = {
                            "name": name_partner,
                            "email": email,
                            "company_type": "person",
                            "mautic_id": val.get("id"),
                            "city": city,
                            "function": cf_cargo_lead_sm,
                            "mobile": personal_phone,
                            "website": cf_url_do_site,
                        }
                        if country_name:
                            country = (
                                self.env["res.country"]
                                .with_context(lang="en_US")
                                .search([("name", "=", country_name)], limit=1)
                            )
                            if country:
                                partner_vals["country_id"] = country.id
                        if state_name:
                            state = self._find_state(state_name, country_name)
                            if state:
                                partner_vals["state_id"] = state.id
                        partner = Partner.create(partner_vals)
                    lead_vals = {
                        "name": name_partner,
                        "email_from": email,
                        "partner_id": partner.id,
                        "type": "opportunity",
                        "partner_name": company_name,
                        "phone": personal_phone,
                        "description": cf_informacoes_adicionais,
                        "function": cf_cargo_lead_sm,
                        "mobile": personal_phone,
                        "website": cf_url_do_site,
                    }
                    if lead_has_mautic_id:
                        lead_vals["mautic_id"] = str(val.get("id"))

                    existing = False
                    if lead_has_mautic_id:
                        existing = Lead.search(
                            [("mautic_id", "=", str(val.get("id")))], limit=1
                        )
                    if not existing:
                        existing = Lead.search(
                            [("email_from", "=ilike", email)], limit=1
                        )

                    if not existing:
                        Lead.create(lead_vals)
                        created.append(email)
                    else:
                        existing.write(lead_vals)
                        updated.append(email)

                    success += 1

                except Exception as e:
                    errors += 1
                    msg = f"Erro no contato {val.get('id')}: {e}"
                    messages.append(msg)
                    _logger.error(msg)

            log_detail = (
                f"Leads criados: {len(created)} ({', '.join(created[:50])})\n"
                f"Leads atualizados: {len(updated)} ({', '.join(updated[:50])})\n"
                f"Ignorados (sem e-mail): {skipped_no_email}\n"
                f"Erros: {errors}\n" + "\n".join(messages[:50])
            )

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "lead",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total,
                    "success_count": success,
                    "error_count": errors,
                    "log_detail": log_detail,
                    "state": "done" if errors == 0 else "partial",
                }
            )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Importação de Leads concluída"),
                    "message": _(
                        "Total: %s | Criados: %s | Atualizados: %s | Ignorados (sem e-mail): %s"
                    )
                    % (total, len(created), len(updated), skipped_no_email),
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error(f"Erro acessando API do Mautic: {e}")
            raise UserError(_("Erro ao buscar dados de Leads do Mautic."))
        except Exception:
            _logger.exception("Erro inesperado na importação de Leads.")
            raise UserError(
                _("Erro inesperado na importação de Leads. Verifique os logs.")
            )
