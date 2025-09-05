# Copyright 2025 - TODAY, Cristiano Mafra Junior <cristiano.mafra@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MauticSegment(models.Model):
    _name = "mautic.segment"
    _description = "Mautic Segment"
    _order = "external_id"

    external_id = fields.Char("Mautic ID", required=True, index=True)
    alias = fields.Char("Alias no Mautic", index=True)
    name_mautic = fields.Char("Nome no Mautic", required=True)
    auto_create_lead = fields.Boolean(
        string="Criar Oportunidades",
        help="Se marcado, contatos deste segmento geram oportunidades no Odoo.",
    )
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
    def import_segments(self):
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
                url = (
                    f"{Company.mautic_api_url}/api/segments?limit={limit}&start={start}"
                )
                res = requests.get(url, headers=headers, timeout=30)
                res.raise_for_status()
                payload = res.json() or {}
                items = (
                    payload.get("lists")
                    or payload.get("segments")
                    or payload.get("data")
                    or {}
                )
                if not items:
                    break

                items_iter = (
                    items.items() if isinstance(items, dict) else enumerate(items)
                )

                for __, val in items_iter:
                    total += 1
                    try:
                        ext_id = str(val.get("id") or "").strip()
                        name = (val.get("name") or "").strip()
                        alias = (val.get("alias") or "").strip()
                        if not ext_id:
                            skipped.append(f"(sem id) start={start}")
                            continue

                        rec = self.sudo().search(
                            [("external_id", "=", ext_id)], limit=1
                        )
                        vals = {
                            "name_mautic": name or ext_id,
                            "alias": alias,
                            "active": True,
                        }

                        if rec:
                            rec.write(vals)
                            updated.append(name or ext_id)
                        else:
                            vals["external_id"] = ext_id
                            vals["auto_create_lead"] = False
                            self.sudo().create(vals)
                            created.append(name or ext_id)

                        success += 1

                    except Exception as e:
                        errors += 1
                        msg = f"Erro no segmento ID {val.get('id')}: {e}"
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
                    "sync_type": "segment",
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
                    "title": _("Importação de Segmentos concluída"),
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
            _logger.error("Erro ao acessar API do Mautic (segments): %s", err)
            raise UserError(
                _("Erro ao buscar segmentos do Mautic. Verifique os logs.")
            ) from err
        except Exception as err:
            _logger.exception("Erro inesperado na importação de segmentos.")
            raise UserError(
                _("Erro inesperado na importação de segmentos. Verifique os logs.")
            ) from err
