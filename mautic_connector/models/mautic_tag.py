# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MauticTag(models.Model):
    _name = "mautic.tag"
    _description = "Mautic Tag"
    _order = "name_mautic"

    external_id = fields.Char("Mautic ID", required=True, index=True)
    name_mautic = fields.Char("Nome no Mautic", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "external_id_unique",
            "unique(external_id)",
            "O ID externo do Mautic deve ser único.",
        ),
    ]

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, rec.name_mautic or ""))
        return result

    @api.model
    def import_tags(self):
        Company = self.env.company
        headers = {
            "Authorization": f"Bearer {Company.mautic_access_token}",
            "Content-Type": "application/json",
        }

        total = success = errors = 0
        created, updated, skipped, messages = [], [], [], []

        try:
            limit, start = 200, 0
            while True:
                url = f"{Company.mautic_api_url}/api/tags?limit={limit}&start={start}"
                res = requests.get(url, headers=headers, timeout=30)
                res.raise_for_status()
                payload = res.json() or {}

                items = payload.get("tags") or payload.get("data") or {}
                if not items:
                    break

                items_iter = (
                    items.items() if isinstance(items, dict) else enumerate(items)
                )

                for __, val in items_iter:
                    total += 1
                    try:
                        ext_id = str(val.get("id") or "").strip()
                        name = (val.get("tag") or val.get("name") or "").strip()
                        if not ext_id:
                            skipped.append("(sem id)")
                            continue

                        rec = self.sudo().search(
                            [("external_id", "=", ext_id)], limit=1
                        )
                        vals = {
                            "name_mautic": name or ext_id,
                            "active": True,
                        }

                        if rec:
                            rec.write(vals)
                            updated.append(name or ext_id)
                        else:
                            vals["external_id"] = ext_id
                            self.sudo().create(vals)
                            created.append(name or ext_id)

                        success += 1

                    except Exception as e:
                        errors += 1
                        msg = f"Erro na tag ID {val.get('id')}: {e}"
                        messages.append(msg)
                        _logger.exception(msg)

                start += limit

            log_detail = (
                f"Criados: {len(created)} ({', '.join(created[:50])})\n"
                f"Atualizados: {len(updated)} ({', '.join(updated[:50])})\n"
                f"Ignorados: {len(skipped)} ({', '.join(skipped[:50])})\n"
                f"Erros: {errors}\n" + "\n".join(messages[:50])
            )

            self.env["mautic.sync.log"].sudo().create(
                {
                    "sync_type": "tag",
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
                    "title": _("Importação de Tags concluída"),
                    "message": _(
                        "Total: %(total)s | Criados: %(created)s | "
                        "Atualizados: %(updated)s | Ignorados: %(skipped)s"
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
            _logger.error("Erro ao acessar API do Mautic (tags): %s", err)
            raise UserError(
                _("Erro ao buscar tags do Mautic. Verifique os logs.")
            ) from err
        except Exception as err:
            _logger.exception("Erro inesperado na importação de tags.")
            raise UserError(
                _("Erro inesperado na importação de tags. Verifique os logs.")
            ) from err
