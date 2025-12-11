# Copyright 2025 - TODAY, Cristiano Mafra ...
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import requests
from dateutil.relativedelta import relativedelta

from odoo import _, models
from odoo.exceptions import UserError


class ResCurrencyRateProviderBCB(models.Model):
    _inherit = "res.currency.rate.provider"

    def _fetch_purchase_rate_from_bcb(self, currency_name, date_str):
        url = (
            "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/"
            "v1/odata/CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
            "?$format=json&$select=cotacaoCompra"
        )
        params = {
            "@moeda": f"'{currency_name}'",
            "@dataCotacao": f"'{date_str}'",
        }
        response = requests.get(url, params=params, timeout=10)
        if not response.ok:
            raise UserError(
                _(
                    "Falha ao consultar cotação de compra no BCB para %(cur)s "
                    "em %(date)s.\n"
                    "Código HTTP: %(status)s"
                )
                % {
                    "cur": currency_name,
                    "date": date_str,
                    "status": response.status_code,
                }
            )

        data = response.json().get("value")
        if not data:
            raise UserError(
                _(
                    "Nenhum dado de cotação de compra retornado pelo BCB "
                    "para %(cur)s em %(date)s."
                )
                % {
                    "cur": currency_name,
                    "date": date_str,
                }
            )

        purchase_value = data[0].get("cotacaoCompra")
        if not purchase_value:
            raise UserError(
                _(
                    "BCB retornou resposta inválida para cotação de compra "
                    "da moeda %(cur)s na data %(date)s."
                )
                % {
                    "cur": currency_name,
                    "date": date_str,
                }
            )

        return purchase_value

    def _update(self, date_from, date_to, newest_only=False):
        res = super()._update(date_from, date_to, newest_only)

        CurrencyRate = self.env["res.currency.rate"]
        currencies = self.currency_ids.mapped("name")

        for day in range((date_to - date_from).days + 1):
            date = date_from + relativedelta(days=day)
            date_str_bcb = date.strftime("%m-%d-%Y")

            for cur in currencies:
                purchase_value = self._fetch_purchase_rate_from_bcb(cur, date_str_bcb)
                purchase_rate = 1 / purchase_value
                rate_rec = CurrencyRate.search(
                    [
                        ("company_id", "=", self.company_id.id),
                        ("currency_id.name", "=", cur),
                        ("name", "=", date),
                    ],
                    limit=1,
                )

                if rate_rec:
                    rate_rec.rate_purchase = purchase_rate

        return res
