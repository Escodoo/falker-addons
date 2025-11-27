# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging
import time
import unicodedata
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
                    "The company does not have Mautic API URL or Access Token configured."  # noqa: E501
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
                        f"ERR: '{partner.display_name}' unexpected response (no contact.id)"  # noqa: E501
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
                    "The company does not have Mautic API URL or Access Token configured."  # noqa: E501
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
                        f"ERR: '{partner.display_name}' unexpected response (no company.id)"  # noqa: E501
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

    def _utm_get_or_create(self, model, raw):
        if raw in (None, "", [], {}):
            return False
        if isinstance(raw, dict):
            raw = raw.get("value")
        if raw in (None, "", [], {}):
            return False
        if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
            rec = self.env[model].sudo().browse(int(raw))
            return rec if rec.exists() else False
        name = str(raw).strip()
        rec = self.env[model].sudo().search([("name", "=", name)], limit=1)
        if rec:
            return rec
        return self.env[model].sudo().create({"name": name})

    def create_leads_from_segments_members(  # noqa: C901
        self,
        only_auto=True,
        page_limit=200,
        max_pages=10,
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
            Partner = self.env["res.partner"].sudo()

            domain = [("active", "=", True)]
            if only_auto:
                domain.append(("auto_create_lead", "=", True))
            segments = Seg.search(domain)

            total_contacts = 0
            created_leads = 0
            skipped_count = 0
            skipped_list = []
            errors = 0
            messages = []
            tag_by_name = {}
            mautic_id_field = Partner._fields.get("mautic_id")
            mautic_id_is_integer = bool(
                mautic_id_field
                and getattr(mautic_id_field, "type", "") in ("integer", "many2one")
            )

            for seg in segments:
                seg_tag_name = seg.name_mautic or seg.external_id
                seg_tag = tag_by_name.get(seg_tag_name)
                if not seg_tag:
                    seg_tag = CrmTag.search(
                        [("name", "=", seg_tag_name)], limit=1
                    ) or CrmTag.create({"name": seg_tag_name})
                    tag_by_name[seg_tag_name] = seg_tag
                base_key = (seg.alias or seg.name_mautic or "").strip()
                if not base_key:
                    messages.append(
                        f"Segmento {seg.external_id} sem alias/nome para busca."
                    )
                    continue
                search_token = f"segment:{base_key}"
                page_count = 0
                start = 0
                while True:
                    if max_pages is not None and page_count >= int(max_pages):
                        break
                    url = (
                        f"{Company.mautic_api_url}/api/contacts"
                        f"?limit={page_limit}"
                        f"&start={start}"
                        f"&search={quote(search_token)}"
                        f"&orderBy=id&orderByDir=DESC"
                    )
                    attempts = 0
                    payload = None
                    while attempts < 3:
                        try:
                            res = requests.get(url, headers=headers, timeout=30)
                            res.raise_for_status()
                            payload = res.json() or {}
                            break
                        except requests.RequestException as e:
                            attempts += 1
                            if attempts >= 3:
                                errors += 1
                                messages.append(
                                    f"Falha ao buscar membros de '{search_token}' (start={start}): {e}"  # noqa: E501
                                )
                            else:
                                time.sleep(1.5 * attempts)

                    if payload is None:
                        break
                    items = payload.get("contacts") or {}
                    if not items:
                        break
                    page = list(items.values() if isinstance(items, dict) else items)
                    batch = len(page)
                    if not batch:
                        break

                    total_contacts += batch
                    page_count += 1
                    cids_str = []
                    for c in page:
                        cid = str(c.get("id") or "").strip()
                        if cid:
                            cids_str.append(cid)
                        else:
                            skipped_count += 1
                            if len(skipped_list) < 1000:
                                skipped_list.append("sem_id_mautic")

                    if not cids_str:
                        start += batch
                        if batch < page_limit:
                            break
                        continue
                    if mautic_id_is_integer:
                        cids_num = []
                        for s in cids_str:
                            try:
                                cids_num.append(int(s))
                            except (ValueError, TypeError):
                                _logger.warning("CID inválido ignorado: %s", s)
                        partner_domain_vals = cids_num
                        key_normalizer = int
                    else:
                        partner_domain_vals = cids_str
                        key_normalizer = str
                    partners = (
                        Partner.search([("mautic_id", "in", partner_domain_vals)])
                        if partner_domain_vals
                        else self.env["res.partner"]
                    )
                    by_mid = {}
                    for p in partners:
                        try:
                            by_mid[key_normalizer(p.mautic_id)] = p
                        except Exception:
                            continue
                    partners_in_page = []
                    for s in cids_str:
                        try:
                            key = key_normalizer(s)
                        except Exception:
                            key = None
                        p = by_mid.get(key)
                        if not p:
                            skipped_count += 1
                            if len(skipped_list) < 1000:
                                skipped_list.append(f"cid={s}")
                            continue
                        partners_in_page.append(p)

                    if not partners_in_page:
                        start += batch
                        if batch < page_limit:
                            break
                        continue

                    partner_ids = [p.id for p in partners_in_page]
                    existing = Lead.with_context(active_test=False).search(
                        [
                            ("partner_id", "in", partner_ids),
                            ("type", "=", "opportunity"),
                        ]
                    )
                    has_lead = set(existing.mapped("partner_id").ids)
                    vals_to_create = []
                    for c in page:
                        cid_s = str(c.get("id") or "").strip()
                        try:
                            key = key_normalizer(cid_s)
                        except Exception:
                            key = None
                        p = by_mid.get(key)
                        if not p:
                            continue
                        if p.id in has_lead:
                            skipped_count += 1
                            if len(skipped_list) < 1000:
                                skipped_list.append(
                                    p.display_name or f"partner_id={p.id}"
                                )
                            continue

                        core = (c.get("fields") or {}).get("core", {}) or {}

                        def _val(k):
                            v = core.get(k) or {}  # noqa: B023
                            return v.get("value") if isinstance(v, dict) else v

                        vals_to_create.append(
                            {
                                "name": p.name,
                                "partner_id": p.id,
                                "email_from": _val("email") or p.email or False,
                                "phone": _val("phone") or p.phone or False,
                                "mobile": _val("mobile")
                                or c.get("mobile")
                                or p.mobile
                                or False,
                                "function": _val("position") or p.function or False,
                                "website": _val("website") or p.website or False,
                                "type": "opportunity",
                                "tag_ids": [(4, tag_by_name[seg_tag_name].id)],
                            }
                        )
                    if vals_to_create:
                        with self.env.cr.savepoint():
                            Lead.create(vals_to_create)
                        created_leads += len(vals_to_create)
                    start += batch
                    if batch < page_limit:
                        break
            detail = (
                f"Contatos processados: {total_contacts} | "
                f"Leads criadas: {created_leads} | "
                f"Ignoradas: {skipped_count} | "
                f"Erros: {errors}\n"
            )
            if skipped_list:
                preview = ", ".join(skipped_list[:1000])
                more = len(skipped_list) - 1000
                detail += f"Ignoradas (amostra): {preview}"
                if more > 0:
                    detail += f"... (+{more} mais)\n"
                else:
                    detail += "\n"
            if messages:
                detail += "\n".join(messages[:50])

            self.env["mautic.sync.log"].sudo().create(
                {
                    "sync_type": "lead",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": total_contacts,
                    "success_count": created_leads,
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

    def update_contacts(self):  # noqa: C901
        self.env.company.refresh_token()
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, updated, skipped = [], [], [], []

        try:
            base = (self.env.company.mautic_api_url or "").rstrip("/")
            limit = 200
            Partner = self.env["res.partner"].sudo()

            def _fetch_contacts(order_by="last_active"):
                query = "search=!is:anonymous"
                url = (
                    f"{base}/api/contacts?"
                    f"limit={limit}&include=tags&{query}&orderBy={order_by}&orderByDir=DESC"
                )
                res = requests.get(url, headers=headers, timeout=30)
                res.raise_for_status()
                result = res.json()
                return result.get("contacts") or {}

            try:
                contacts = _fetch_contacts("last_active")
            except requests.HTTPError:
                contacts = _fetch_contacts("id")

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

                    mautic_id = val.get("id")
                    existing = False
                    if mautic_id:
                        existing = Partner.search(
                            [("mautic_id", "=", mautic_id), ("is_company", "=", False)],
                            limit=1,
                        )

                    my_dict = {
                        "name": full_name,
                        "mautic_id": mautic_id,
                        "street": (core.get("address1") or {}).get("value") or "",
                        "street2": (core.get("address2") or {}).get("value") or "",
                        "mobile": (core.get("mobile") or {}).get("value")
                        or (core.get("cf_temp_mobile") or {}).get("value")
                        or "",
                        "phone": (core.get("phone") or {}).get("value")
                        or (core.get("cf_temp_phone") or {}).get("value")
                        or "",
                        "email": email,
                        "zip": (core.get("zipcode") or {}).get("value") or "",
                        "website": (core.get("website") or {}).get("value") or "",
                        "function": (core.get("position") or {}).get("value") or "",
                        "company_type": "person",
                        "is_company": False,
                        "vat": (core.get("cf_cnpj_cpf") or {}).get("value") or "",
                        "ref": (core.get("cf_ref_do_contato") or {}).get("value") or "",
                        "comment": (core.get("cf_informacoes_adicionais") or {}).get(
                            "value"
                        )
                        or "",
                        "l10n_br_ie_code": (core.get("cf_inscricao") or {}).get("value")
                        or "",
                        "district": (core.get("cf_bairro") or {}).get("value") or "",
                    }
                    utm_campaign_raw = (core.get("cf_utm_campaign") or {}).get("value")
                    utm_medium_raw = (core.get("cf_utm_medium") or {}).get("value")
                    utm_source_raw = (core.get("cf_utm_source") or {}).get("value")

                    utm_campaign = self._utm_get_or_create(
                        "utm.campaign", utm_campaign_raw
                    )
                    utm_medium = self._utm_get_or_create("utm.medium", utm_medium_raw)
                    utm_source = self._utm_get_or_create("utm.source", utm_source_raw)

                    ident = (core.get("cf_conversion_identifier") or {}).get(
                        "value"
                    ) or ""
                    installed_langs = set(
                        self.env["res.lang"]
                        .sudo()
                        .search([("active", "=", True)])
                        .mapped("code")
                    )

                    def _lang_from_ident(ident_l: str) -> str:
                        if ident_l in ("form-cotacao-eua", "form-cotacao-en"):
                            return "en_US"
                        if ident_l == "form-cotacao-es":
                            return "es_ES"
                        if ident_l == "form-cotacao-br":
                            return "pt_BR"
                        return "pt_BR"

                    country_name = (core.get("country") or {}).get("value")
                    if country_name:
                        country_id = (
                            self.env["res.country"]
                            .with_context(lang="en_US")
                            .search([("name", "=", country_name)], limit=1)
                        )
                        lang_code = _lang_from_ident(ident)
                        if lang_code in installed_langs:
                            my_dict["lang"] = lang_code
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
                            [("is_company", "=", True), ("name", "=", partner_name)],
                            limit=1,
                        )
                        if company:
                            my_dict["parent_id"] = company.id
                            my_dict["type"] = "private"
                    custom = self._extract_mautic_custom_fields(val)
                    if custom:
                        my_dict["mautic_custom_fields"] = custom

                    if existing:
                        ALLOWED_UPDATES = {"mautic_custom_fields"}
                        diffs = {}
                        for k in ALLOWED_UPDATES:
                            if k not in my_dict:
                                continue
                            new_v = my_dict[k]
                            if new_v in ("", None, False, [], {}):
                                continue
                            cur_v = existing[k]
                            cur_cmp = getattr(cur_v, "id", cur_v)
                            new_cmp = getattr(new_v, "id", new_v)
                            if cur_cmp != new_cmp:
                                diffs[k] = new_v
                        if diffs:
                            existing.write(diffs)
                            updated.append(full_name)
                            partner = existing
                        else:
                            skipped.append(full_name)
                            partner = existing
                    else:
                        if utm_campaign:
                            my_dict["campaign_id"] = utm_campaign.id
                        if utm_medium:
                            my_dict["medium_id"] = utm_medium.id
                        if utm_source:
                            my_dict["source_id"] = utm_source.id
                        partner = Partner.create(my_dict)
                        created.append(full_name)
                    tag_ids = self._extract_tag_ids(val)
                    if tag_ids:
                        TagModel = self.env["mautic.tag"].sudo()
                        Category = self.env["res.partner.category"].sudo()
                        has_partner_mautic_tag_field = (
                            "mautic_tag_ids" in Partner._fields
                        )
                        tags_found = TagModel.search([("external_id", "in", tag_ids)])
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
                    msg = f"Error processing contact ID {val.get('id')}: {str(e)}"
                    messages.append(msg)
                    _logger.error(msg)
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

    def _extract_mautic_company_custom_fields(self, company_dict: dict):
        out = {}
        fields = company_dict.get("fields") or {}
        fields_all = fields.get("all", {}) or {}
        fields_core = fields.get("core", {}) or {}

        def _val(v):
            return (v or {}).get("value") if isinstance(v, dict) else v

        source = {}
        source.update(fields_all)
        for k, v in fields_core.items():
            source.setdefault(k, v)
        NATIVE = {
            "companyname",
            "companyemail",
            "companywebsite",
            "companyaddress1",
            "companyaddress2",
            "companycity",
            "companystate",
            "companyzipcode",
            "companycountry",
            "cf_cnpj_cpf_comp",
            "cf_bairro_comp",
            "cf_comentario_comp",
            "cf_ref_do_contato_comp",
            "cf_inscricao_comp",
        }

        for key, raw in source.items():
            if key in NATIVE:
                continue
            val = _val(raw)
            if val in (None, "", [], {}):
                continue
            out[key] = val

        return out

    def import_company(self):  # noqa: C901
        self.env.company.refresh_token()
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }
        total = success = errors = 0
        messages, created, updated, skipped = [], [], [], []

        try:
            limit, start = 300, 0
            Partner = self.env["res.partner"].sudo()
            base = (self.env.company.mautic_api_url or "").rstrip("/")
            while True:
                url = f"{base}/api/companies?limit={limit}&start={start}"
                res = requests.get(url=url, headers=headers, timeout=30)
                res.raise_for_status()
                companies = res.json().get("companies", {}) or {}
                if not companies:
                    break

                for __, val in companies.items():
                    total += 1
                    name = ""
                    try:
                        company_fields = val.get("fields") or {}
                        fields_all = company_fields.get("all", {}) or {}
                        fields_core = company_fields.get("core", {}) or {}

                        def v(d, k):
                            x = d.get(k) or {}
                            return (x.get("value") if isinstance(x, dict) else x) or ""

                        name = v(fields_core, "companyname")
                        email = v(fields_core, "companyemail")
                        name_norm = self._norm(name)
                        mautic_id = val.get("id")
                        existing = Partner.search(
                            [("mautic_id", "=", mautic_id)], limit=1
                        )
                        if not existing and email:
                            existing = Partner.search(
                                [("email", "=", email), ("is_company", "=", True)],
                                limit=1,
                            )
                        if not existing and name:
                            exact = Partner.search(
                                [("is_company", "=", True), ("name", "=", name)],
                                limit=1,
                            )
                            if exact:
                                existing = exact
                            else:
                                for p in Partner.search(
                                    [("is_company", "=", True), ("name", "ilike", name)]
                                ):
                                    if self._norm(p.name) == name_norm:
                                        existing = p
                                        break
                        data_dict = {
                            "mautic_id": mautic_id,
                            "website": v(fields_all, "companywebsite"),
                            "zip": v(fields_all, "companyzipcode"),
                            "street": v(fields_all, "companyaddress1"),
                            "street2": v(fields_all, "companyaddress2"),
                            "vat": v(fields_all, "cf_cnpj_cpf_comp"),
                            "district": v(fields_all, "cf_bairro_comp"),
                            "comment": v(fields_all, "cf_comentario_comp"),
                            "ref": v(fields_all, "cf_ref_do_contato_comp"),
                            "l10n_br_ie_code": v(fields_all, "cf_inscricao_comp"),
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

                        city_name = fields_all.get("companycity") or ""
                        if city_name:
                            city_id = self.env["res.city"].search(
                                [("name", "=", city_name)], limit=1
                            )
                            if city_id:
                                data_dict["city_id"] = city_id.id
                        company_custom = self._extract_mautic_company_custom_fields(val)
                        if company_custom:
                            data_dict["mautic_custom_fields"] = company_custom
                        if not existing:
                            Partner.create(data_dict)
                            created.append(name or f"ID {mautic_id}")
                        else:
                            diffs = {}
                            for k, new_v in data_dict.items():
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
                                updated.append(name or f"ID {mautic_id}")
                            else:
                                skipped.append(name or f"ID {mautic_id}")

                        success += 1

                    except Exception as e:
                        errors += 1
                        msg = (
                            f"Error processing company ID {val.get('id')} "
                            f"({name}): {str(e)}"
                        )
                        messages.append(msg)

                start += limit

            log_detail = (
                f"Created: {len(created)} ({', '.join(created)})\n"
                f"Updated: {len(updated)} ({', '.join(updated)})\n"
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
                        "Total: %(total)s | Criadas: %(created)s | Atualizadas: %(updated)s | Ignoradas: %(skipped)s"  # noqa: E501
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
