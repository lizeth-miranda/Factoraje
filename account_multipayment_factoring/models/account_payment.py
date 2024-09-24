# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields
from odoo.tools.float_utils import float_round, float_is_zero


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    factoring_move = fields.Many2one('account.move', string='Factoring Move', copy=False,
                                     help='Factoring Move used in MultiPayment')

    factoring_partner = fields.Many2one('res.partner', string='Factoring Partner', copy=False, )

    def amount_total_factoring(self):
        if self.factoring_move:
            related_lines = self.factoring_move.line_ids
            return sum(related_lines.mapped('credit') or [])
        return 0.0

    def _related_moves_factoring(self):
        vals = {}
        if self.factoring_move:
            related_lines = self.factoring_move.line_ids
            debit_moves = related_lines.mapped('matched_debit_ids')
            for line in debit_moves:
                account_move = line.debit_move_id.move_id
                vals.setdefault(account_move,
                                {'payment_amount': 0.0})
                vals[account_move]['payment_amount'] += line.amount
        return vals

    def _compute_factoring_move_taxes(self, invoice_vals_list=None):
        factoring_moves_vals = self._related_moves_factoring()
        global_vals = {
            'invoice_ids': {},
            'taxes': {},
            'amount_total': 0.0,
        }
        taxes_keys = ['TotalTrasladosImpuestoIVA16', 'TotalTrasladosBaseIVA16', 'TotalTrasladosBaseIVA0',
                      'TotalTrasladosImpuestoIVA0', 'TotalTrasladosBaseIVAExento', 'TotalTrasladosBaseIVA8',
                      'TotalTrasladosImpuestoIVA8', 'total_amount']
        global_vals['taxes'] = {key: 0.0 for key in taxes_keys}

        for invoice_vals in invoice_vals_list:
            invoice = invoice_vals['invoice']
            if invoice not in factoring_moves_vals:
                continue
            total = factoring_moves_vals[invoice]['payment_amount']
            global_vals['amount_total'] += total
            percentage_paid = total / invoice.amount_total
            precision = invoice.currency_id.decimal_places
            sign = 1
            taxes_totales = {key: 0.0 for key in taxes_keys}
            taxes_totales['total_amount'] = total
            taxes = list(invoice_vals['tax_details_transferred']['tax_details'].values())
            if taxes:
                tax_amount = int(taxes[0]['tax'].amount) / 100
                base_amount = invoice_vals['tax_details_transferred']['base_amount_currency']
                base_val_proportion = float_round(abs(base_amount) * percentage_paid * sign, precision)
                tax_val_proportion = float_round(base_val_proportion * tax_amount, precision)
                if taxes[0]['tax'].l10n_mx_tax_type == 'Tasa':
                    taxes_totales['TotalTrasladosBaseIVA{}'.format(int(tax_amount * 100))] = float_round(
                        base_val_proportion, precision_rounding=self.currency_id.rounding)
                    taxes_totales['TotalTrasladosImpuestoIVA{}'.format(int(tax_amount * 100))] = float_round(
                        tax_val_proportion, precision_rounding=self.currency_id.rounding)
                else:
                    taxes_totales['TotalTrasladosBaseIVAExento'] = float_round(
                        base_val_proportion, precision_rounding=self.currency_id.rounding)
                global_vals['invoice_ids'][invoice] = taxes_totales

        if global_vals['invoice_ids']:
            for invoice in global_vals['invoice_ids']:
                for key, value in global_vals['invoice_ids'][invoice].items():
                    global_vals['taxes'].setdefault(key, 0.0)
                    global_vals['taxes'][key] += value

        return global_vals
