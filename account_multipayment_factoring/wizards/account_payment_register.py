# Copyright 2026 Munin
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'



    factoring_total = fields.Monetary(string='Total Factoraje')


