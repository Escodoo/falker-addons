{
    'name': 'Sale Price Control',
    'version': '14.0.1.0.0',
    'summary': 'Bloqueia edição manual dos campos price_unit e fiscal_price em linhas de venda',
    'author': 'Falker, Édison',
    'depends': ['sale', 'l10n_br_sale'],
    'data': [
        'views/sale_order_line_view.xml',
    ],
    'installable': True,
    'application': False,
}