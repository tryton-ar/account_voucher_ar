#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelWorkflow, ModelView, ModelSQL, fields
from decimal import Decimal
from trytond.pyson import Eval, In
from trytond.pool import Pool

_STATES = {
    'readonly': In(Eval('state'), ['posted']),
}


class AccountVoucherPayMode(ModelSQL, ModelView):
    'Account Voucher Pay Mode'
    _name = 'account.voucher.paymode'
    _description = __doc__

    name = fields.Char('Name')
    account_id = fields.Many2One('account.account', 'Account')

AccountVoucherPayMode()


class AccountVoucher(ModelWorkflow, ModelSQL, ModelView):
    'Account Voucher'
    _name = 'account.voucher'
    _description = __doc__

    def __init__(self):
        super(AccountVoucher, self).__init__()
        self._error_messages.update({
            'partial_pay': 'Partial Payments are not allowed (yet)!',
        })

    def init(self, module_name):
        super(AccountVoucher, self).init(module_name)

    def on_change_pay_amount_1(self, vals):
        res = {}
        amount = vals.get('pay_amount_1') + vals.get('pay_amount_2')
        res['amount'] = amount
        return res

    def on_change_pay_amount_2(self, vals):
        res = {}
        res['amount'] = vals.get('pay_amount_1') + vals.get('pay_amount_2')
        return res

    def amount_total(self, ids, name):
        res = {}
        for voucher in self.browse(ids):
            res[voucher.id] = voucher.pay_amount_1 + voucher.pay_amount_2
        return res

    def pay_amount(self, ids, name):
        res = {}
        total = 0
        for voucher in self.browse(ids):
            if voucher.line_ids:
                for line in voucher.line_ids:
                    total += line.amount_original
            res[voucher.id] = total
        return res

    def prepare_moves(self, voucher_id):
        move_obj = Pool().get('account.move')
        period_obj = Pool().get('account.period')
        voucher = Pool().get('account.voucher').browse(voucher_id.id)
        new_moves = []
        if voucher.amount != voucher.amount_pay:
            self.raise_user_error('partial_pay')
        move_id = move_obj.create({
            'name': voucher.number,
            'period': period_obj.find(1, date=voucher.date),
            'journal': voucher.journal_id.id,
            'date': voucher.date,
        })

        #
        # Pay Mode 1
        #
        if voucher.pay_mode_1 and voucher.pay_amount_1:
            if voucher.voucher_type == 'receipt':
                debit = Decimal(str(voucher.pay_amount_1))
                credit = Decimal('0.00')
            else:
                debit = Decimal('0.00')
                credit = Decimal(str(voucher.pay_amount_1))

            new_moves.append({
                'name': voucher.number,
                'debit': debit,
                'credit': credit,
                'account': voucher.pay_mode_1.account_id.id,
                'move': move_id,
                'journal': voucher.journal_id.id,
                'period': period_obj.find(1, date=voucher.date),
                'party': voucher.party.id,
            })

        #
        # Pay Mode 2
        #
        if voucher.pay_mode_2 and voucher.pay_amount_2:
            if voucher.voucher_type == 'receipt':
                debit = Decimal(str(voucher.pay_amount_2))
                credit = Decimal('0.00')
            else:
                debit = Decimal('0.00')
                credit = Decimal(str(voucher.pay_amount_2))

            new_moves.append({
                'name': voucher.number,
                'debit': debit,
                'credit': credit,
                'account': voucher.pay_mode_2.account_id.id,
                'move': move_id,
                'journal': voucher.journal_id.id,
                'period': period_obj.find(1, date=voucher.date),
                'date': voucher.date,
                'party': voucher.party.id,
            })

        #
        # Voucher Lines
        #
        if voucher.line_ids:
            line_move_ids = []
            for line in voucher.line_ids:
                line_move_ids.append(line.move_line_id.id)
                if voucher.voucher_type == 'receipt':
                    debit = Decimal('0.00')
                    credit = Decimal(str(line.amount_original))
                else:
                    debit = Decimal(str(line.amount_original))
                    credit = Decimal('0.00')

                new_moves.append({
                    'name': voucher.number,
                    'debit': debit,
                    'credit': credit,
                    'account': line.account_id.id,
                    'move': move_id,
                    'journal': voucher.journal_id.id,
                    'period': period_obj.find(1, date=voucher.date),
                    'date': voucher.date,
                    'party': voucher.party.id,
                })

        return {
            'new_moves': new_moves,
            'invoice_moves': line_move_ids,
            'voucher_id': voucher.id,
            'move_id': move_id,
        }

    def create_moves(self, pay_moves, invoice_moves, voucher_id):
        move_line_obj = Pool().get('account.move.line')
        created_moves = []
        to_reconcile = []
        for move_line in pay_moves:
            created_moves.append(move_line_obj.create(move_line))

        for line in move_line_obj.browse(created_moves):
            if line.account.reconcile:
                to_reconcile.append(line.id)
        for invoice_line in invoice_moves:
            to_reconcile.append(invoice_line)

        move_line_obj.reconcile(to_reconcile)

        self.write(voucher_id, {'state': 'posted'})
        return True

    def action_paid(self, voucher_id):
        params = self.prepare_moves(voucher_id)
        self.create_moves(
                params.get('new_moves'),
                params.get('invoice_moves'),
                params.get('voucher_id'),
            )
        return True

    def action_draft(self, voucher_id):
        self.write(voucher_id.id, {'state': 'draft'})

    def action_cancel(self, voucher_id):
        self.write(voucher_id.id, {'state': 'cancel'})

    def default_state(self):
        return 'draft'

    number = fields.Char('Number', required=True, help="Voucher Number",
        states=_STATES)

    party = fields.Many2One('party.party', 'Party', required=True,
        states=_STATES)

    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', select='1', required=True, states=_STATES)

    name = fields.Char('Memo', size=256, states=_STATES)

    pay_mode_1 = fields.Many2One('account.voucher.paymode', 'Pay Mode 1',
        states=_STATES)

    pay_amount_1 = fields.Float('Pay Amount 1',
        on_change=['pay_amount_1', 'pay_amount_2'], states=_STATES)

    pay_mode_2 = fields.Many2One('account.voucher.paymode', 'Pay Mode 2',
        states=_STATES)

    pay_amount_2 = fields.Float('Pay Amount 2',
        on_change=['pay_amount_1', 'pay_amount_2'], states=_STATES)

    date = fields.Date('Date', required=True, states=_STATES)

    journal_id = fields.Many2One('account.journal', 'Journal', required=True,
        states=_STATES)

    period_id = fields.Many2One('account.period', 'Period')

    currency_id = fields.Many2One('currency.currency', 'Currency',
        states=_STATES)

    company_id = fields.Many2One('company.company', 'Company', states=_STATES)

    line_ids = fields.One2Many('account.voucher.line', 'voucher_id', 'Lines',
        states=_STATES)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('proforma', 'Pro-forma'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
        ], 'State', select='1', readonly=True)
    amount = fields.Function(fields.Float('Pago'), 'amount_total')

    amount_pay = fields.Function(fields.Float('Deuda'), 'pay_amount')

AccountVoucher()


class AccountVoucherLine(ModelSQL, ModelView):
    'Account Voucher Line'
    _name = 'account.voucher.line'
    _description = __doc__

    voucher_id = fields.Many2One('account.voucher', 'Voucher')
    name = fields.Char('Name')
    account_id = fields.Many2One('account.account', 'Account')
    amount = fields.Float('Amount')
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select='1')
    move_line_id = fields.Many2One('account.move.line', 'Move Line')
    amount_original = fields.Float('Original Amount')
    amount_unreconciled = fields.Float('Unreconciled amount')

AccountVoucherLine()
