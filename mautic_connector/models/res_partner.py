# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging
import unicodedata

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountAssetProfile(models.Model):
    _inherit = "account.asset.profile"
    x_type_id = fields.Char("x_type_id")


class ResPartner(models.Model):
    _inherit = "res.partner"
    mautic_company_id = fields.Char("mautic_company_id")
    mautic_id = fields.Char("Mautic ID")
    mautic_exported = fields.Boolean("mautic_exported", default=False)
    mautic_is_update = fields.Boolean("mautic_is_update", default=False)

    @api.model
    def _split_name(self, name):
        parts = name.strip().split()
        firstname = parts[0] if parts else ""
        middlename = " ".join(parts[1:-1]) if len(parts) > 2 else ""
        lastname = parts[-1] if len(parts) > 1 else ""
        return firstname, middlename, lastname

    def export_contact(self):  # noqa: C901
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
                    except Exception:
                        pass
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
                    except Exception:
                        pass
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
