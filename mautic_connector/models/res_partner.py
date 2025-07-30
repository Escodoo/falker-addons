# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging

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
    mautic_id = fields.Char("ID")
    mautic_exported = fields.Boolean("mautic_exported", default=False)
    mautic_is_update = fields.Boolean("mautic_is_update", default=False)

    @api.model
    def _split_name(self, name):
        parts = name.strip().split()
        firstname = parts[0] if parts else ""
        middlename = " ".join(parts[1:-1]) if len(parts) > 2 else ""
        lastname = parts[-1] if len(parts) > 1 else ""
        return firstname, middlename, lastname

    def export_contact(self):
        if len(self) > 1:
            raise UserError(_("Please select only one contact at a time."))
        if self.mautic_id or self.mautic_exported:
            raise UserError(_("This contact has already been exported to Mautic."))
        if not self.env.company.mautic_access_token:
            raise UserError(
                _("The associated company does not have an access token for Mautic.")
            )
        firstname, middlename, lastname = self._split_name(self.name)
        payload = {
            "firstname": firstname,
            "middlename": middlename,
            "lastname": lastname,
            "email": self.email or f"{firstname}.{lastname}@odoo.com",
            "city": self.city or "",
            "state": self.state_id.name if self.state_id else "",
            "country": self.country_id.with_context(lang="en_US").name
            if self.country_id
            else "",
            "zipcode": self.zip or "",
            "phone": self.phone or "",
            "address1": self.street or "",
            "address2": self.street2 or "",
            "isuser": True,
        }
        if self.parent_id and self.parent_id.name:
            payload["company"] = self.parent_id.name

        url = f"{self.env.company.mautic_api_url}/api/contacts/new"
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url, data=json.dumps(payload), headers=headers, timeout=30
            )
            response.raise_for_status()
            res = response.json()

            contact_data = res.get("contact")
            if contact_data and contact_data.get("id"):
                self.write(
                    {
                        "mautic_id": str(contact_data["id"]),
                        "mautic_exported": True,
                    }
                )
                self.env["mautic.sync.log"].create(
                    {
                        "sync_type": "contact",
                        "execution_time": fields.Datetime.now(),
                        "total_processed": 1,
                        "success_count": 1,
                        "error_count": 0,
                        "log_detail": f"Contact '{self.name}' "
                        "exported successfully (Mautic ID: {self.mautic_id}).",
                        "state": "done",
                    }
                )
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Importação concluída"),
                        "sticky": False,
                        "type": "success",
                    },
                }
            else:
                error_message = f"Error exporting contact '{self.name}'"
                self.env["mautic.sync.log"].create(
                    {
                        "sync_type": "contact",
                        "execution_time": fields.Datetime.now(),
                        "total_processed": 1,
                        "success_count": 0,
                        "error_count": 1,
                        "log_detail": error_message,
                        "state": "error",
                    }
                )
                raise UserError(
                    _("Unexpected response from Mautic when exporting contact.")
                )

        except requests.RequestException as e:
            raise UserError(_("Error communicating with Mautic: %s") % str(e))

    @api.model
    def export_company(self):  # noqa: C901
        if len(self) > 1:
            raise UserError(_("Please select only one record at a time."))

        if self.company_type != "company":
            raise UserError(_("This record is not a company."))

        if not self.env.company.mautic_access_token:
            raise UserError(
                _("The company does not have a Mautic access token configured.")
            )

        url = f"{self.env.company.mautic_api_url}/api/companies/new"
        headers = {
            "Authorization": f"Bearer {self.env.company.mautic_access_token}",
            "Content-Type": "application/json",
        }
        data_dict = {}
        if self.name:
            data_dict["companyname"] = self.name
        if self.phone:
            data_dict["companyphone"] = self.phone
        if self.email:
            data_dict["companyemail"] = self.email
        if self.website:
            data_dict["companywebsite"] = self.website
        if self.street:
            data_dict["companyaddress1"] = self.street
        if self.street2:
            data_dict["companyaddress2"] = self.street2
        if self.city:
            data_dict["companycity"] = self.city
        if self.zip:
            data_dict["companyzipcode"] = self.zip
        if self.state_id:
            data_dict["companystate"] = self.state_id.name
        if self.country_id:
            country_name_en = self.country_id.with_context(lang="en_US").name
            data_dict["companycountry"] = country_name_en

        data_dict["isuser"] = True
        payload = json.dumps(data_dict)
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=30)
            response.raise_for_status()
            res = response.json()
            company_data = res.get("company")
            if company_data and company_data.get("id"):
                mautic_id = company_data.get("id")
                self.write(
                    {
                        "mautic_id": str(mautic_id),
                        "mautic_exported": True,
                    }
                )
                self.env["mautic.sync.log"].create(
                    {
                        "sync_type": "company",
                        "execution_time": fields.Datetime.now(),
                        "total_processed": 1,
                        "success_count": 1,
                        "error_count": 0,
                        "log_detail": f"Empresa '{self.name}' "
                        "exportada com sucesso (ID Mautic: {mautic_id}).",
                        "state": "done",
                    }
                )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Importação concluída"),
                        "sticky": False,
                        "type": "success",
                    },
                }
            else:
                raise UserError(
                    _("Error exporting company: unexpected response from Mautic.")
                )
        except requests.RequestException as e:
            error_message = f"Erro ao exportar '{self.name}' para o Mautic: {str(e)}"

            self.env["mautic.sync.log"].create(
                {
                    "sync_type": "company",
                    "execution_time": fields.Datetime.now(),
                    "total_processed": 1,
                    "success_count": 0,
                    "error_count": 1,
                    "log_detail": error_message,
                    "state": "error",
                }
            )

            raise UserError(_("Error communicating with Mautic: %s") % str(e))

    @api.model
    def cron_export_company_to_mautic(self):
        partners = self.search(
            [
                ("mautic_exported", "=", False),
                ("is_company", "=", True),
            ],
            limit=1,
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
