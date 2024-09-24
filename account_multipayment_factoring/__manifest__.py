# Copyright 2026 Munin
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Account Multipayment Factoring',
    'description': """
        Agrega l10n_mx Factoraje en los Multi Pagos""",
    'version': '16.0.1.0.0',
    'license': 'AGPL-3',
    'author': 'Munin',
    'depends': [
        'account_multipayment_general',
    ],
    'data': [
        'data/payment20.xml',
        'views/res_partner_view.xml',
        'wizards/multi_payments_general.xml',
    ],
    'demo': [
    ],
}
