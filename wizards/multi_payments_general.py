# Copyright 2026 Munin
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MultiPaymentsGeneral(models.TransientModel):
    _inherit = "multi.payments.general"

    is_factoring = fields.Boolean(string="Aplicar Factoraje", default=False)
    l10n_mx_edi_factoring_id = fields.Many2one("res.partner", "Factorante", copy=False, )
    invoice_supplier = fields.Many2one(comodel_name="account.move",
                                       string="Factura de Proovedor")
    move_line_ids = fields.Many2many(string="Asientos Factoraje",
                                     comodel_name="account.move.line", compute="_compute_move_lines")
    amount_residual_factoring = fields.Monetary(string="Monto Disponible",
                                                readonly=True, compute="_compute_factoring_vals",
                                                help="Monto disponible para factoraje")
    factoring_currency_id = fields.Many2one('res.currency', string='Moneda', related='invoice_supplier.currency_id')

    @api.onchange('is_factoring')
    def _onchange_is_factoring(self):
        for record in self:
            if not record.is_factoring:
                record.invoice_supplier = False
                record.l10n_mx_edi_factoring_id = False
                for line in record.register_payment_line:
                    line.factoring_total = 0

    @api.depends('register_payment_line', 'invoice_supplier')
    def _compute_factoring_vals(self):
        for record in self:
            record.amount_residual_factoring = record.invoice_supplier.amount_residual

    @api.depends('invoice_supplier')
    def _compute_move_lines(self):
        move_lines = self.invoice_supplier.line_ids
        move_line_ids = move_lines.filtered(lambda line: line.account_id.account_type in ('asset_receivable',
                                                                                          'liability_payable'))
        self.move_line_ids = [(6, 0, move_line_ids.ids)]

    def _pre_create_action(self):
        res = super(MultiPaymentsGeneral, self)._pre_create_action()
        if self.is_factoring:
            factoring_move = self.create_factoring_moves()
            res['factoring_move'] = factoring_move
        return res

    def _extra_payment_move_vals(self, partner, amount_payment, **kwargs):
        res = super(MultiPaymentsGeneral, self)._extra_payment_move_vals(partner, amount_payment, **kwargs)
        if 'factoring_move' in kwargs:
            res['factoring_move'] = kwargs['factoring_move'].id
            res['factoring_partner'] = self.l10n_mx_edi_factoring_id.id
        return res

    def create_factoring_moves(self):
        move_lines = self.register_payment_line.filtered(lambda x: x.factoring_total > 0).line_ids + \
                     self.invoice_supplier.line_ids
        move_lines = move_lines.filtered(
            lambda line: line.account_type in ('asset_receivable', 'liability_payable') and not line.reconciled)
        if any(move_lines.mapped("reconciled")):
            raise UserError(_("All entries must not been reconciled"))
        if len(move_lines.mapped("account_id")) == 1:
            raise UserError(
                _(
                    "The 'Compensate' function is intended to balance "
                    "operations on different accounts for the same partner.\n"
                    "In this case all selected entries belong to the same "
                    "account.\n Please use the 'Reconcile' function."
                )
            )
        if len(self.register_payment_line.mapped("partner_id")) > 2 or len(move_lines.mapped("partner_id")) < 2:
            raise UserError(
                _(
                   "No se puede generar factoraje a facturas de clientes diferentes"
                )
            )
        if len(move_lines.mapped("partner_id")) < 1:
            raise UserError(
                _(
                    "Se debe seleccionar al menos una factura de cliente"
                )
            )
        debit_move_lines_debit = move_lines.filtered("debit")
        move = self.env["account.move"].create(
            {"ref": _("AR/AP netting"), "journal_id": self.journal_id.id,
             "currency_id": self.currency_id.id,
             'is_multipayment_factoring': True,
             'move_type': 'entry'}
        )
        # Group default amounts by account
        account_groups = move_lines.read_group(
            [("id", "in", move_lines.ids)],
            ["account_id", "amount_residual"],
            ["account_id"],
        )
        debtors = []  # supplier invoice that has  + balance
        creditors = []  # invoices that has - balance
        total_debtors = 0
        total_creditors = 0
        # group accounts by invoices and vendor bills
        for account_group in account_groups:
            balance = account_group["amount_residual"]
            partner = move_lines.filtered(lambda x: x.account_id.id == account_group["account_id"][0]
                                          ).partner_id.id
            group_vals = {
                "account_id": account_group["account_id"][0],
                "balance": abs(balance),
                "partner_id": partner,
            }
            if balance > 0:
                debtors.append(group_vals)
                total_debtors += balance
            else:
                creditors.append(group_vals)
                total_creditors += abs(balance)
        # Change for custom balance on debtors.
        debtors = []
        total_debtors = 0
        for debit_line in debit_move_lines_debit:
            payment_line = self.register_payment_line.filtered(lambda x: debit_line in x.line_ids)
            group_vals = {
                "account_id": debit_line.account_id.id,
                "balance": abs(payment_line.factoring_total),
                "partner_id": debit_line.partner_id.id,
                "payment_line": payment_line.id,
            }
            debtors.append(group_vals)
            total_debtors += abs(payment_line.factoring_total)

        # Create move lines
        netting_amount = min(total_creditors, total_debtors)
        field_map = {1: "debit", 0: "credit"}
        new_move_lines = []
        for i, group in enumerate([debtors, creditors]):
            available_amount = netting_amount
            for account_group in group:
                if account_group["balance"] > available_amount:
                    amount = netting_amount
                else:
                    amount = account_group["balance"]
                move_line_vals = {
                    field_map[i]: amount,
                    "partner_id": account_group["partner_id"],
                    "name": move.ref,
                    "display_type": "payment_term",
                    "account_id": account_group["account_id"],
                    "currency_id": self.currency_id.id,
                    "temp_id_factoring": account_group.get("payment_line", 0),
                }
                new_move_lines.append((0, 0, move_line_vals))
        if new_move_lines:
            move.write({"line_ids": new_move_lines})
        # Make reconciliation
        if move.state != 'posted':
            move.action_post()
        payment_lines = move.line_ids

        lines = self.register_payment_line.filtered(lambda x: x.factoring_total > 0)

        for account in payment_lines.account_id:
            for line in lines:
                invoice_lines = line.line_ids
                payment_line = payment_lines.filtered(lambda x: x.temp_id_factoring == line.id)
                (payment_line + invoice_lines) \
                    .filtered_domain([('account_id', '=', account.id), ('reconciled', '=', False)]) \
                    .reconcile()

        for move_line in move.line_ids.filtered(lambda x: not x.reconciled):
            to_reconcile = move_line + move_lines.filtered(
                lambda x: x.account_id == move_line.account_id
            )
            to_reconcile.reconcile()
        return move

    def check_payment_validity(self):
        super(MultiPaymentsGeneral, self).check_payment_validity()
        if self.is_factoring:
            for line in self.register_payment_line:
                if line.factoring_total > line.payment_difference:
                    raise UserError(_("El monto a facturar + factoraje no puede ser mayor al saldo de la factura"))
                if line.source_currency_id != self.currency_id:
                    raise UserError(_("No se puede realizar un facroraje de diferentes monedas"))
        return True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    temp_id_factoring = fields.Integer(string='Temp ID Factoring')

