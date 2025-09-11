# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MAUTIC_NATIVE_KEYS = {
    "firstname",
    "lastname",
    "name",
    "email",
    "position",
    "company",
    "company_name",
    "phone",
    "mobile",
    "personal_phone",
    "website",
    "address1",
    "address2",
    "city",
    "state",
    "zipcode",
    "country",
    "title",
    "timezone",
    "preferred_locale",
    "id",
    "dateAdded",
    "dateModified",
    "last_active",
    "owner",
    "points",
    "ipAddress",
}


class ResPartner(models.Model):
    _inherit = "res.partner"
    mautic_id = fields.Char(string="Mautic ID", readonly=True)
    mautic_exported = fields.Boolean("mautic_exported", default=False, readonly=True)
    mautic_is_update = fields.Boolean("mautic_is_update", default=False, readonly=True)
    mautic_custom_fields = fields.Text(readonly=True)

    @api.model
    def _split_name(self, name):
        parts = name.strip().split()
        firstname = parts[0] if parts else ""
        middlename = " ".join(parts[1:-1]) if len(parts) > 2 else ""
        lastname = parts[-1] if len(parts) > 1 else ""
        return firstname, middlename, lastname

    def _extract_mautic_custom_fields(self, contact_dict: dict):
        out = {}

        fields_all = (contact_dict.get("fields") or {}).get("all", {}) or {}
        fields_core = (contact_dict.get("fields") or {}).get("core", {}) or {}

        def _val(v):
            return (v or {}).get("value") if isinstance(v, dict) else v

        source = {}
        source.update(fields_all)
        for k, v in fields_core.items():
            source.setdefault(k, v)

        for key, raw in source.items():
            if key in _MAUTIC_NATIVE_KEYS:
                continue
            val = _val(raw)
            if val in (None, "", [], {}):
                continue
            out[key] = val

        return out

    def export_contact(self):  # noqa: C901
        if not self:
            return

        comp = self.env.company
        comp.refresh_token()
        if not (comp.mautic_api_url and comp.mautic_access_token):
            raise UserError(
                _(
                    "The company does not have Mautic API URL or Access Token configured."
                )
            )

        base = (comp.mautic_api_url or "").rstrip("/")
        headers = {
            "Authorization": f"Bearer {comp.mautic_access_token}",
            "Content-Type": "application/json",
        }
        create_url = f"{base}/api/contacts/new"

        total = len(self)
        success = skipped = errors = 0
        details = []

        for partner in self.sudo():
            if partner.company_type != "person":
                skipped += 1
                details.append(
                    f"Skip: '{partner.display_name}' is not a contact (person)."
                )
                continue
            if partner.mautic_id:
                check_url = f"{base}/api/contacts/{partner.mautic_id}"
                try:
                    r = requests.get(check_url, headers=headers, timeout=30)
                    if r.status_code == 404:
                        partner.write({"mautic_id": False, "mautic_exported": False})
                    else:
                        r.raise_for_status()
                        skipped += 1
                        details.append(
                            f"Skip: '{partner.display_name}' already exported "
                            f"(Mautic ID {partner.mautic_id})."
                        )
                        continue
                except requests.RequestException as e:
                    _logger.warning(
                        "Error checking contact %s on Mautic: %s",
                        partner.display_name,
                        e,
                    )
            firstname, middlename, lastname = self._split_name(partner.name or "")
            payload = {
                "firstname": firstname,
                "middlename": middlename,
                "lastname": lastname,
                "email": partner.email or "",
                "city": partner.city or "",
                "country": partner.country_id.with_context(lang="en_US").name
                if partner.country_id
                else "",
                "zipcode": partner.zip or "",
                "phone": partner.phone or "",
                "address1": partner.street or "",
                "address2": partner.street2 or "",
                "isuser": True,
            }
            if partner.state_id:
                st = unicodedata.normalize("NFKD", partner.state_id.name or "")
                st = "".join(c for c in st if not unicodedata.combining(c))
                payload["state"] = st
            if partner.parent_id and partner.parent_id.name:
                payload["company"] = partner.parent_id.name

            resp = None
            try:
                resp = requests.post(
                    create_url, data=json.dumps(payload), headers=headers, timeout=30
                )
                resp.raise_for_status()
                data = resp.json() or {}
                contact_data = data.get("contact") or {}
                mautic_id = contact_data.get("id")

                if mautic_id:
                    partner.write(
                        {"mautic_id": str(mautic_id), "mautic_exported": True}
                    )
                    success += 1
                    details.append(
                        f"OK: '{partner.display_name}' → Mautic ID {mautic_id}"
                    )
                else:
                    errors += 1
                    details.append(
                        f"ERR: '{partner.display_name}' unexpected response (no contact.id)"
                    )

            except requests.RequestException as e:
                msg = str(e)
                if resp is not None:
                    try:
                        err_json = resp.json()
                        if isinstance(err_json, dict) and "errors" in err_json:
                            extra = "; ".join(
                                err.get("message", "") for err in err_json["errors"]
                            )
                            if extra:
                                msg = f"{msg} | {extra}"
                    except Exception as err:
                        _logger.debug(
                            "Falha ao interpretar resposta JSON do Mautic: %s", err
                        )
                errors += 1
                details.append(f"ERR: '{partner.display_name}' → {msg}")

        self.env["mautic.sync.log"].create(
            {
                "sync_type": "contact",
                "execution_time": fields.Datetime.now(),
                "total_processed": total,
                "success_count": success,
                "error_count": errors,
                "log_detail": "\n".join(details[-200:]),
                "state": "done" if errors == 0 else ("partial" if success else "error"),
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export finished"),
                "message": _(
                    "Total: %(t)s | Exported: %(s)s | Skipped: %(k)s | Errors: %(e)s"
                )
                % {"t": total, "s": success, "k": skipped, "e": errors},
                "type": "success" if errors == 0 else "warning",
                "sticky": False,
            },
        }

    @api.model
    def export_company(self):  # noqa: C901
        self.env.company.refresh_token()
        if not self:
            return

        comp = self.env.company
        if not (comp.mautic_api_url and comp.mautic_access_token):
            raise UserError(
                _(
                    "The company does not have Mautic API URL or Access Token configured."
                )
            )

        base = (comp.mautic_api_url or "").rstrip("/")
        headers = {
            "Authorization": f"Bearer {comp.mautic_access_token}",
            "Content-Type": "application/json",
        }
        create_url = f"{base}/api/companies/new"

        total = len(self)
        success = skipped = errors = 0
        details = []

        for partner in self.sudo():
            if partner.company_type != "company":
                skipped += 1
                details.append(f"Skip: '{partner.display_name}' is not a company.")
                continue

            if partner.mautic_id:
                check_url = f"{base}/api/companies/{partner.mautic_id}"
                try:
                    r = requests.get(check_url, headers=headers, timeout=30)
                    if r.status_code == 404:
                        partner.write({"mautic_id": False, "mautic_exported": False})
                    else:
                        r.raise_for_status()
                        skipped += 1
                        details.append(
                            f"Skip: '{partner.display_name}' already exported "
                            f"(Mautic ID {partner.mautic_id})."
                        )
                        continue
                except requests.RequestException as e:
                    _logger.warning(
                        "Error checking company %s on Mautic: %s",
                        partner.display_name,
                        e,
                    )

            data = {}
            if partner.name:
                data["companyname"] = partner.name[:64]
            if partner.phone:
                data["companyphone"] = partner.phone
            if partner.email:
                data["companyemail"] = partner.email
            if partner.website:
                data["companywebsite"] = partner.website
            if partner.street:
                data["companyaddress1"] = partner.street
            if partner.street2:
                data["companyaddress2"] = partner.street2
            if partner.city:
                data["companycity"] = partner.city
            if partner.zip:
                data["companyzipcode"] = partner.zip
            if partner.state_id:
                st = unicodedata.normalize("NFKD", partner.state_id.name)
                st = "".join(c for c in st if not unicodedata.combining(c))
                data["companystate"] = st
            if partner.country_id:
                data["companycountry"] = partner.country_id.with_context(
                    lang="en_US"
                ).name
            data["isuser"] = True

            resp = None
            try:
                resp = requests.post(
                    create_url, data=json.dumps(data), headers=headers, timeout=30
                )
                resp.raise_for_status()
                payload = resp.json() or {}
                company_data = payload.get("company") or {}
                mautic_id = company_data.get("id")
                if mautic_id:
                    partner.write(
                        {
                            "mautic_id": str(mautic_id),
                            "mautic_exported": True,
                        }
                    )
                    success += 1
                    details.append(
                        f"OK: '{partner.display_name}' → Mautic ID {mautic_id}"
                    )
                else:
                    errors += 1
                    details.append(
                        f"ERR: '{partner.display_name}' unexpected response (no company.id)"
                    )
            except requests.RequestException as e:
                msg = str(e)
                if resp is not None:
                    try:
                        err_json = resp.json()
                        if isinstance(err_json, dict) and "errors" in err_json:
                            extra = "; ".join(
                                err.get("message", "") for err in err_json["errors"]
                            )
                            if extra:
                                msg = f"{msg} | {extra}"
                    except Exception as err:
                        _logger.debug(
                            "Falha ao interpretar resposta JSON do Mautic: %s", err
                        )
                errors += 1
                details.append(f"ERR: '{partner.display_name}' → {msg}")

        self.env["mautic.sync.log"].create(
            {
                "sync_type": "company",
                "execution_time": fields.Datetime.now(),
                "total_processed": total,
                "success_count": success,
                "error_count": errors,
                "log_detail": "\n".join(details[-200:]),
                "state": "done" if errors == 0 else ("partial" if success else "error"),
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export finished"),
                "message": _(
                    "Total: %(t)s | Exported: %(s)s | Skipped: %(k)s | Errors: %(e)s"
                )
                % {"t": total, "s": success, "k": skipped, "e": errors},
                "type": "success" if errors == 0 else "warning",
                "sticky": False,
            },
        }

    @api.model
    def cron_export_company_to_mautic(self):
        partners = self.search(
            [
                ("mautic_exported", "=", False),
                ("is_company", "=", True),
            ],
            limit=100,
        )

        for partner in partners:
            try:
                partner.export_company()
                _logger.info(f"Empresa '{partner.name}' exportada com sucesso.")
            except Exception as e:
                _logger.error(f"Erro ao exportar empresa '{partner.name}': {str(e)}")

    @api.model
    def cron_export_contacts_to_mautic(self):
        contacts = self.search(
            [
                ("mautic_exported", "=", False),
                ("mautic_id", "=", False),
                ("is_company", "=", False),
            ]
        )
        for contact in contacts:
            try:
                contact.export_contact()
            except Exception as e:
                _logger.error(f"Erro ao exportar contato ID {contact.id}: {e}")

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

    def _extract_tag_ids(self, contact: dict):
        result = []
        tags = contact.get("tags") or []
        if isinstance(tags, list):
            for t in tags:
                if t and t.get("id") is not None:
                    result.append(str(t["id"]).strip())
        elif isinstance(tags, dict):
            for t in tags.values():
                if t and t.get("id") is not None:
                    result.append(str(t["id"]).strip())
        seen, out = set(), []
        for x in result:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    def create_leads_from_segments_members(  # noqa: C901
        self, only_auto=True, page_limit=200
    ):
        try:
            Company = self.env.company.sudo()
            Company.refresh_token()
            headers = {
                "Authorization": f"Bearer {Company.mautic_access_token}",
                "Content-Type": "application/json",
            }
            Seg = self.env["mautic.segment"].sudo()
            Lead = self.env["crm.lead"].sudo()
            CrmTag = self.env["crm.tag"].sudo()

            domain = [("active", "=", True)]
            if only_auto:
                domain.append(("auto_create_lead", "=", True))
            segments = Seg.search(domain)

            total_contacts = 0
            created_leads = 0
            updated_leads = 0
            errors = 0
            messages = []

            partner_by_mautic = {}
            tag_by_name = {}

            for seg in segments:
                seg_tag_name = seg.name_mautic or seg.external_id
                seg_tag = tag_by_name.get(seg_tag_name)
                if not seg_tag:
                    seg_tag = CrmTag.search([("name", "=", seg_tag_name)], limit=1)
                    if not seg_tag:
                        seg_tag = CrmTag.create({"name": seg_tag_name})
                    tag_by_name[seg_tag_name] = seg_tag

                search_token = f"segment:{(seg.alias or seg.name_mautic or '').strip()}"
                if not search_token.endswith(":") and not (
                    seg.alias or seg.name_mautic
                ):
                    messages.append(
                        f"Segmento {seg.external_id} sem alias/nome para busca."
                    )
                    continue

                start = 0
                while True:
                    url = (
                        f"{Company.mautic_api_url}/api/contacts"
                        f"?limit={page_limit}&start={start}&search={quote(search_token)}"
                    )
                    try:
                        res = requests.get(url, headers=headers, timeout=30)
                        res.raise_for_status()
                        payload = res.json() or {}
                    except Exception as e:
                        errors += 1
                        messages.append(
                            f"Falha ao buscar membros de '{search_token}': {e}"
                        )
                        break

                    items = payload.get("contacts") or {}
                    if not items:
                        break

                    batch = 0
                    iter_items = (
                        items.items() if isinstance(items, dict) else enumerate(items)
                    )
                    for __, c in iter_items:
                        batch += 1
                        total_contacts += 1
                        try:
                            cid = str(c.get("id") or "").strip()
                            if not cid:
                                continue

                            partner = partner_by_mautic.get(cid)
                            if partner is None:
                                partner = self.sudo().search(
                                    [("mautic_id", "=", cid)], limit=1
                                )
                                partner_by_mautic[cid] = partner or False
                            if not partner:
                                continue

                            core = (c.get("fields") or {}).get("core", {}) or {}

                            def _val(k):
                                v = core.get(k) or {}
                                return v.get("value") if isinstance(v, dict) else v

                            lead_vals = {
                                "name": partner.name,
                                "partner_id": partner.id,
                                "email_from": _val("email") or partner.email or False,
                                "phone": _val("phone") or partner.phone or False,
                                "mobile": _val("mobile")
                                or c.get("mobile")
                                or partner.mobile
                                or False,
                                "function": _val("position")
                                or partner.function
                                or False,
                                "website": _val("website") or partner.website or False,
                                "type": "opportunity",
                                "tag_ids": [(4, tag_by_name[seg_tag_name].id)],
                            }

                            lead = Lead.search(
                                [("partner_id", "=", partner.id)], limit=1
                            )
                            if not lead and partner.email:
                                lead = Lead.search(
                                    [("email_from", "=ilike", partner.email)], limit=1
                                )

                            if lead:
                                lead.write(lead_vals)
                                updated_leads += 1
                            else:
                                Lead.create(lead_vals)
                                created_leads += 1

                        except Exception as e:
                            errors += 1
                            messages.append(f"Contato seg '{search_token}' erro: {e}")

                    if batch < page_limit:
                        break
                    start += page_limit

            detail = (
                f"Contatos: {total_contacts} | Leads C/A: "
                f"{created_leads}/{updated_leads} | Erros: {errors}\n"
                + "\n".join(messages[:50])
            )
            self.env["mautic.sync.log"].sudo().create(
                {
                    "sync_type": "lead",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total_contacts,
                    "success_count": created_leads + updated_leads,
                    "error_count": errors,
                    "log_detail": detail,
                    "state": "done" if errors == 0 else "partial",
                }
            )
            return None

        except (requests.RequestException, ValueError) as e:
            _logger.error("Error accessing Mautic contacts API: %s", e)
            raise UserError(
                _("Error fetching contact data from Mautic. Check logs.")
            ) from e

        except Exception as err:
            _logger.exception("Unexpected error importing segment members.")
            raise UserError(
                _("Unexpected error importing segment members. Check logs.")
            ) from err

    def import_contacts(self):  # noqa: C901
        self.env.company.refresh_token()
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, updated, skipped = [], [], [], []

        try:
            ICP = self.env["ir.config_parameter"].sudo()
            base = (self.env.company.mautic_api_url or "").rstrip("/")
            limit = 200  # máx por execução

            bootstrap_done = (
                ICP.get_param("mautic.contacts.bootstrap_done") or ""
            ).strip() == "1"
            Partner = self.env["res.partner"].sudo()

            # =========================
            # MODO 1: BOOTSTRAP (criar todos; NÃO atualiza existentes)
            # =========================
            if not bootstrap_done:
                start = int(ICP.get_param("mautic.contacts.bootstrap_start", "0") or 0)
                url = f"{base}/api/contacts?limit={limit}&start={start}&include=tags,lists&orderBy=id&orderByDir=ASC"  # noqa: B950

                max_retries, attempt = 3, 0
                while True:
                    res = requests.get(url, headers=headers, timeout=30)
                    if res.status_code in (429, 500, 502, 503, 504):
                        attempt += 1
                        if attempt > max_retries:
                            res.raise_for_status()
                        delay = 2**attempt
                        _logger.warning(
                            "Mautic %s (bootstrap start=%s). Retry %s em %ss",
                            res.status_code,
                            start,
                            attempt,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                    res.raise_for_status()
                    break

                result = res.json()
                contacts = result.get("contacts") or {}

                for __, val in contacts.items():
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
                            [
                                ("mautic_id", "=", val.get("id")),
                                ("is_company", "=", False),
                            ],
                            limit=1,
                        )
                        if not existing and email:
                            existing = Partner.search(
                                [("email", "=", email), ("is_company", "=", False)],
                                limit=1,
                            )
                        if not existing and full_name_norm:
                            existing = Partner.search(
                                [("name", "=", full_name), ("is_company", "=", False)],
                                limit=1,
                            )
                            if not existing:
                                candidates = Partner.search(
                                    [
                                        ("is_company", "=", False),
                                        ("name", "ilike", full_name),
                                    ]
                                )
                                for p in candidates:
                                    if self._norm(p.name) == self._norm(full_name):
                                        existing = p
                                        break

                        if existing:
                            skipped.append(full_name or f"ID {val.get('id')}")
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
                            "website": (core.get("website") or {}).get("value") or "",
                            "function": (core.get("position") or {}).get("value") or "",
                            "company_type": "person",
                            "is_company": False,
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
                            state_id = self._find_state(state_name, country_name)
                            if state_id:
                                my_dict["state_id"] = state_id.id

                        city_name = (core.get("city") or {}).get("value")
                        if city_name:
                            city_id = self.env["res.city"].search(
                                [("name", "=", city_name)], limit=1
                            )
                            if city_id:
                                my_dict["city_id"] = city_id.id

                        partner_name = (core.get("company") or {}).get("value")
                        if partner_name:
                            company = Partner.search(
                                [
                                    ("is_company", "=", True),
                                    ("name", "=", partner_name),
                                ],
                                limit=1,
                            )
                            if company:
                                my_dict["parent_id"] = company.id

                        custom = self._extract_mautic_custom_fields(val)
                        if custom:
                            my_dict["mautic_custom_fields"] = custom

                        partner = Partner.create(my_dict)
                        created.append(full_name)
                        tag_ids = self._extract_tag_ids(val)
                        if tag_ids:
                            TagModel = self.env["mautic.tag"].sudo()
                            Category = self.env["res.partner.category"].sudo()
                            has_partner_mautic_tag_field = (
                                "mautic_tag_ids" in Partner._fields
                            )
                            tags_found = TagModel.search(
                                [("external_id", "in", tag_ids)]
                            )
                            cat_ids = set(partner.category_id.ids)
                            for t in tags_found:
                                display = t.name_mautic or t.external_id
                                cat = Category.search([("name", "=", display)], limit=1)
                                if not cat:
                                    cat = Category.create({"name": display})
                                cat_ids.add(cat.id)
                            writes = {"category_id": [(6, 0, list(cat_ids))]}
                            if has_partner_mautic_tag_field:
                                writes["mautic_tag_ids"] = [(6, 0, tags_found.ids)]
                            partner.write(writes)

                        success += 1

                    except Exception as e:
                        errors += 1
                        messages.append(
                            f"Error processing contact ID {val.get('id')}: {str(e)}"
                        )
                        _logger.error(messages[-1])
                next_start = start + len(contacts)
                ICP.set_param("mautic.contacts.bootstrap_start", str(next_start))
                if not contacts:
                    ICP.set_param("mautic.contacts.bootstrap_done", "1")

                    cursor_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
                    ICP.set_param(
                        "mautic.contacts.last_modified",
                        cursor_dt.isoformat().replace("+00:00", "Z"),
                    )

            # =========================
            # MODO 2: INCREMENTAL — “últimos modificados/criados” via WHERE
            # =========================
            else:

                def _parse_dt(v):
                    if not v:
                        return None
                    if isinstance(v, (int, float)):
                        return datetime.fromtimestamp(float(v), tz=timezone.utc)
                    s = str(v).strip()
                    if s.isdigit():
                        return datetime.fromtimestamp(float(s), tz=timezone.utc)
                    try:
                        return datetime.fromisoformat(
                            s.replace("Z", "+00:00")
                        ).astimezone(timezone.utc)
                    except Exception:
                        return None

                def _fmt_sql(dt_utc):
                    # 'YYYY-MM-DD HH:MM:SS' em UTC (Mautic aceita este formato no where[val])
                    return dt_utc.strftime("%Y-%m-%d %H:%M:%S")

                last_mod_key = "mautic.contacts.last_modified"
                last_mod_str = (ICP.get_param(last_mod_key) or "").strip()
                last_mod_dt = _parse_dt(last_mod_str) or (
                    datetime.now(timezone.utc) - timedelta(days=3650)
                )
                where_val = _fmt_sql(last_mod_dt)

                def _fetch_contacts_where(col_name, quota, include_lists=False):
                    fetched = []
                    start = 0
                    page_size = min(200, quota)
                    while len(fetched) < quota:
                        params = {
                            "limit": page_size,
                            "start": start,
                            "include": "tags,lists" if include_lists else "tags",
                            "orderBy": col_name,
                            "orderByDir": "DESC",
                            "where[0][col]": col_name,
                            "where[0][expr]": "gte",
                            "where[0][val]": where_val,
                        }
                        attempt, max_retries = 0, 3
                        while True:
                            try:
                                res = requests.get(
                                    f"{base}/api/contacts",
                                    headers=headers,
                                    params=params,
                                    timeout=30,
                                )
                                if (
                                    res.status_code in (429, 500, 502, 503, 504)
                                    and include_lists
                                ):
                                    attempt += 1
                                    if attempt <= max_retries:
                                        time.sleep(2**attempt)
                                        continue
                                    return _fetch_contacts_where(
                                        col_name,
                                        quota - len(fetched),
                                        include_lists=False,
                                    )
                                res.raise_for_status()
                                break
                            except requests.RequestException as e:
                                raise e
                        data = res.json() or {}
                        chunk = list((data.get("contacts") or {}).values())
                        if not chunk:
                            break
                        fetched.extend(chunk)
                        if len(chunk) < page_size:
                            break
                        start += len(chunk)
                    return fetched[:quota]

                remaining = limit
                contacts_list = []

                try:
                    contacts_list.extend(
                        _fetch_contacts_where(
                            "date_modified", remaining, include_lists=False
                        )
                    )
                except requests.RequestException as e:
                    msg = f"Incremental fetch (date_modified) falhou: {e.__class__.__name__}: {e}"  # noqa: B950
                    messages.append(msg)
                    _logger.warning(msg, exc_info=True)

                remaining = limit - len(contacts_list)
                if remaining > 0:
                    try:
                        contacts_list.extend(
                            _fetch_contacts_where(
                                "date_added", remaining, include_lists=False
                            )
                        )
                    except requests.RequestException as e:
                        msg = f"Incremental fetch (date_added) falhou: {e.__class__.__name__}: {e}"  # noqa: B950
                        messages.append(msg)
                        _logger.warning(msg, exc_info=True)

                def _extract_dm(v):
                    return (
                        _parse_dt(v.get("dateModified"))
                        or _parse_dt(v.get("lastModified"))
                        or _parse_dt(v.get("lastActive"))
                        or _parse_dt(v.get("dateAdded"))
                        or datetime.fromtimestamp(0, tz=timezone.utc)
                    )

                contacts_list.sort(key=lambda v: _extract_dm(v), reverse=True)
                max_seen_dt = last_mod_dt
                for val in contacts_list:
                    dm_dt = _extract_dm(val)
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
                            [
                                ("mautic_id", "=", val.get("id")),
                                ("is_company", "=", False),
                            ],
                            limit=1,
                        )
                        if not existing and email:
                            existing = Partner.search(
                                [("email", "=", email), ("is_company", "=", False)],
                                limit=1,
                            )
                        existing_name = None
                        if not existing and full_name_norm:
                            existing_name = Partner.search(
                                [("name", "=", full_name), ("is_company", "=", False)],
                                limit=1,
                            )
                            if not existing_name:
                                candidates = Partner.search(
                                    [
                                        ("is_company", "=", False),
                                        ("name", "ilike", full_name),
                                    ]
                                )
                                for p in candidates:
                                    if self._norm(p.name) == self._norm(full_name):
                                        existing_name = p
                                        break
                        if existing_name and not existing:
                            skipped.append(full_name)
                            if dm_dt and dm_dt > max_seen_dt:
                                max_seen_dt = dm_dt
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
                            "website": (core.get("website") or {}).get("value") or "",
                            "function": (core.get("position") or {}).get("value") or "",
                            "company_type": "person",
                            "is_company": False,
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
                            state_id = self._find_state(state_name, country_name)
                            if state_id:
                                my_dict["state_id"] = state_id.id

                        city_name = (core.get("city") or {}).get("value")
                        if city_name:
                            city_id = self.env["res.city"].search(
                                [("name", "=", city_name)], limit=1
                            )
                            if city_id:
                                my_dict["city_id"] = city_id.id

                        partner_name = (core.get("company") or {}).get("value")
                        if partner_name:
                            company = Partner.search(
                                [
                                    ("is_company", "=", True),
                                    ("name", "=", partner_name),
                                ],
                                limit=1,
                            )
                            if company:
                                my_dict["parent_id"] = company.id

                        custom = self._extract_mautic_custom_fields(val)
                        if custom:
                            my_dict["mautic_custom_fields"] = custom

                        if not existing:
                            partner = Partner.create(my_dict)
                            created.append(full_name)
                        else:
                            diffs = {}
                            for k, new_v in my_dict.items():
                                if k not in existing._fields:
                                    continue
                                if new_v in ("", None, False, [], {}):
                                    continue
                                if k in (
                                    "mautic_id",
                                    "mautic_custom_fields",
                                ) and existing[k] not in (False, None, "", 0, {}):
                                    continue
                                cur_v = existing[k]
                                cur_cmp = getattr(cur_v, "id", cur_v)
                                new_cmp = getattr(new_v, "id", new_v)
                                if cur_cmp != new_cmp:
                                    diffs[k] = new_v

                            if diffs:
                                existing.write(diffs)
                                partner = existing
                                updated.append(full_name)
                            else:
                                partner = existing
                                skipped.append(full_name)
                        tag_ids = self._extract_tag_ids(val)
                        if tag_ids:
                            TagModel = self.env["mautic.tag"].sudo()
                            Category = self.env["res.partner.category"].sudo()
                            has_partner_mautic_tag_field = (
                                "mautic_tag_ids" in Partner._fields
                            )
                            tags_found = TagModel.search(
                                [("external_id", "in", tag_ids)]
                            )
                            new_cat_ids = set(partner.category_id.ids)
                            for t in tags_found:
                                display = t.name_mautic or t.external_id
                                cat = Category.search([("name", "=", display)], limit=1)
                                if not cat:
                                    cat = Category.create({"name": display})
                                new_cat_ids.add(cat.id)
                            writes = {}
                            if set(partner.category_id.ids) != new_cat_ids:
                                writes["category_id"] = [(6, 0, list(new_cat_ids))]
                            if has_partner_mautic_tag_field and set(
                                partner.mautic_tag_ids.ids
                            ) != set(tags_found.ids):
                                writes["mautic_tag_ids"] = [(6, 0, tags_found.ids)]
                            if writes:
                                partner.write(writes)

                        success += 1
                        if dm_dt and dm_dt > max_seen_dt:
                            max_seen_dt = dm_dt

                    except Exception as e:
                        errors += 1
                        messages.append(
                            f"Error processing contact ID {val.get('id')}: {str(e)}"
                        )
                        _logger.error(messages[-1])

                if max_seen_dt:
                    new_cursor = (max_seen_dt - timedelta(minutes=5)).astimezone(
                        timezone.utc
                    )
                    ICP.set_param(
                        "mautic.contacts.last_modified",
                        new_cursor.isoformat().replace("+00:00", "Z"),
                    )
            try:
                self.env["res.partner"].sudo().create_leads_from_segments_members(
                    only_auto=True,
                    page_limit=200,
                )
            except Exception as e:
                _logger.warning("Pós-import: falha ao criar leads por segmentos: %s", e)
            log_detail = (
                f"Created: {len(created)} ({', '.join(created)})\n"
                f"Updated: {len(updated)} ({', '.join(updated)})\n"
                f"Skipped: {len(skipped)} ({', '.join(skipped)})\n"
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
                        "Total: %(total)s | Criadas: %(created)s | "
                        "Atualizadas: %(updated)s | Ignoradas: %(skipped)s"
                    )
                    % {
                        "total": total,
                        "created": len(created),
                        "updated": len(updated),
                        "skipped": len(skipped),
                    },
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as e:
            _logger.error("Error accessing Mautic contacts API: %s", e)
            raise UserError(
                _("Error fetching contact data from Mautic. Check logs.")
            ) from e

        except Exception as err:
            _logger.exception("Unexpected error importing contacts.")
            raise UserError(
                _("Unexpected error importing contacts. Check logs.")
            ) from err

    def import_company(self):  # noqa: C901
        self.env.company.refresh_token()
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, skipped = [], [], []

        try:
            limit, start = 100, 0
            while True:
                url = (
                    f"{self.env.company.mautic_api_url}/api/companies"
                    f"?limit={limit}&start={start}"
                )
                res = requests.get(
                    url=url,
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
                            [("mautic_id", "=", val.get("id"))], limit=1
                        )
                        # TODO: Pode ter parceiro diferente com mesmo e-mail
                        if not existing and email:
                            existing = Partner.search(
                                [("email", "=", email), ("is_company", "=", True)],
                                limit=1,
                            )
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
                            "mautic_id": val.get("id"),
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

                        city_name = (fields_all.get("companycity") or "",)
                        if city_name:
                            city_id = self.env["res.city"].search(
                                [("name", "=", city_name)], limit=1
                            )
                            if city_id:
                                data_dict["city_id"] = city_id.id

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
                    "message": _(
                        "Total: %(total)s | Criadas: %(created)s | Ignoradas: %(skipped)s"
                    )
                    % {
                        "total": total,
                        "created": len(created),
                        "skipped": len(skipped),
                    },
                    "sticky": False,
                    "type": "success",
                },
            }

        except (requests.RequestException, ValueError) as err:
            _logger.error("Erro ao acessar API do Mautic: %s", err)
            raise UserError(
                _("Error fetching company data from Mautic. Check logs.")
            ) from err

        except Exception as err:
            _logger.exception("Unexpected error importing companies.")
            raise UserError(
                _("Unexpected error importing companies. Check logs.")
            ) from err
