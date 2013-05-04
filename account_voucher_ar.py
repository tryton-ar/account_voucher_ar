#This file is part of the account_voucher_ar module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from decimal import Decimal
from trytond.model import ModelSingleton, ModelView, ModelSQL, fields
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.transaction import Transaction
from trytond.pyson import Eval, In
from trytond.pool import Pool

__all__ = ['AccountVoucherSequence', 'AccountVoucherPayMode', 'AccountVoucher',
    'AccountVoucherLine', 'AccountVoucherLinePaymode', 'SelectInvoicesAsk',
    'SelectInvoices', ]

_STATES = {
    'readonly': In(Eval('state'), ['posted']),
}


class AccountVoucherSequence(ModelSingleton, ModelSQL, ModelView):
    'Account Voucher Sequence'
    __name__ = 'account.voucher.sequence'

    voucher_sequence = fields.Property(fields.Many2One('ir.sequence',
        'Voucher Sequence', required=True,
        domain=[('code', '=', 'account.voucher')]))


class AccountVoucherPayMode(ModelSQL, ModelView):
    'Account Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'

    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account')


class AccountVoucher(ModelSQL, ModelView):
    'Account Voucher'
    __name__ = 'account.voucher'
    _rec_name = 'number'

    number = fields.Char('Number', readonly=True, help="Voucher Number")
    party = fields.Many2One('party.party', 'Party', required=True,
        states=_STATES)
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', select=True, required=True, states=_STATES)
    name = fields.Char('Memo', size=256, states=_STATES)
    pay_lines = fields.One2Many('account.voucher.line.paymode', 'voucher',
        'Pay Mode Lines', states=_STATES)
    date = fields.Date('Date', required=True, states=_STATES)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        states=_STATES)
    currency = fields.Many2One('currency.currency', 'Currency', required=True,
        states=_STATES)
    company = fields.Many2One('company.company', 'Company', required=True,
        states=_STATES)
    lines = fields.One2Many('account.voucher.line', 'voucher', 'Lines',
        states=_STATES)
    comment = fields.Text('Comment', states=_STATES)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ], 'State', select=True, readonly=True)
    amount = fields.Function(fields.Numeric('Payment', digits=(16, 2)),
        'amount_total')
    amount_pay = fields.Function(fields.Numeric('To Pay', digits=(16, 2)),
        'pay_amount')

    @classmethod
    def __setup__(cls):
        super(AccountVoucher, cls).__setup__()
        cls._error_messages.update({
            'partial_pay': 'Partial Payments are not allowed (yet)!',
        })
        cls._buttons.update({
                'post': {
                    'invisible': Eval('state') == 'posted',
                    },
                'select_invoices': {
                    'invisible': Eval('state') == 'posted',
                    },
                })

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.id

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @classmethod
    def set_number(cls, voucher):
        Sequence = Pool().get('ir.sequence')
        AccountVoucherSequence = Pool().get('account.voucher.sequence')

        sequence = AccountVoucherSequence(1)
        cls.write([voucher], {'number': Sequence.get_id(
            sequence.voucher_sequence.id)})

    def amount_total(self, name):
        res = Decimal('0.0')
        if self.pay_lines:
            for line in self.pay_lines:
                res += line.pay_amount
        return res

    def pay_amount(self, name):
        total = 0
        if self.lines:
            for line in self.lines:
                total += line.amount_original
        return total

    @classmethod
    def prepare_moves(cls, voucher):
        Move = Pool().get('account.move')
        Period = Pool().get('account.period')

        move_lines = []
        if voucher.amount != voucher.amount_pay:
            cls.raise_user_error('partial_pay')
        move, = Move.create([{
            'period': Period.find(1, date=voucher.date),
            'journal': voucher.journal.id,
            'date': voucher.date,
        }])

        #
        # Pay Modes
        #
        if voucher.pay_lines:
            for line in voucher.pay_lines:
                if voucher.voucher_type == 'receipt':
                    debit = line.pay_amount
                    credit = Decimal('0.0')
                else:
                    debit = Decimal('0.0')
                    credit = line.pay_amount

                move_lines.append({
                    'debit': debit,
                    'credit': credit,
                    'account': line.pay_mode.account.id,
                    'move': move.id,
                    'journal': voucher.journal.id,
                    'period': Period.find(1, date=voucher.date),
                    'party': voucher.party.id,
                })

        #
        # Voucher Lines
        #
        if voucher.lines:
            line_move_ids = []
            for line in voucher.lines:
                line_move_ids.append(line.move_line)
                if voucher.voucher_type == 'receipt':
                    debit = Decimal('0.00')
                    credit = Decimal(str(line.amount_original))
                else:
                    debit = Decimal(str(line.amount_original))
                    credit = Decimal('0.00')

                move_lines.append({
                    'debit': debit,
                    'credit': credit,
                    'account': line.account.id,
                    'move': move.id,
                    'journal': voucher.journal.id,
                    'period': Period.find(1, date=voucher.date),
                    'date': voucher.date,
                    'party': voucher.party.id,
                })
        return {
            'move_lines': move_lines,
            'invoice_moves': line_move_ids,
            'voucher': voucher,
            'move': move,
        }

    @classmethod
    def create_moves(cls, pay_moves, invoice_moves, voucher, move):
        Move = Pool().get('account.move')
        MoveLine = Pool().get('account.move.line')

        to_reconcile = []
        created_moves = MoveLine.create(pay_moves)
        Move.post([move])
        for line in created_moves:
            if line.account.reconcile:
                to_reconcile.append(line)
        for invoice_line in invoice_moves:
            to_reconcile.append(invoice_line)
        MoveLine.reconcile(to_reconcile)
        return True

    @classmethod
    @ModelView.button
    def post(cls, vouchers):
        cls.set_number(vouchers[0])
        params = cls.prepare_moves(vouchers[0])
        cls.create_moves(
                params.get('move_lines'),
                params.get('invoice_moves'),
                params.get('voucher'),
                params.get('move'),
            )
        cls.write([vouchers[0]], {'state': 'posted'})

    @classmethod
    @ModelView.button_action('account_voucher_ar.wizard_select_invoices')
    def select_invoices(cls, ids):
        pass


class AccountVoucherLine(ModelSQL, ModelView):
    'Account Voucher Line'
    __name__ = 'account.voucher.line'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account')
    amount = fields.Numeric('Amount', digits=(16, 2))
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True)
    move_line = fields.Many2One('account.move.line', 'Move Line')
    amount_original = fields.Numeric('Original Amount', digits=(16, 2))
    amount_unreconciled = fields.Numeric('Unreconciled amount', digits=(16, 2))


class AccountVoucherLinePaymode(ModelSQL, ModelView):
    'Account Voucher Line Pay Mode'
    __name__ = 'account.voucher.line.paymode'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    pay_mode = fields.Many2One('account.voucher.paymode', 'Pay Mode',
        required=True, states=_STATES)
    pay_amount = fields.Numeric('Pay Amount', digits=(16, 2), required=True,
        states=_STATES)


class SelectInvoicesAsk(ModelView):
    'Select Invoices Ask'
    __name__ = 'account.voucher.select_invoices.ask'

    lines = fields.Many2Many('account.move.line', None, None,
        'Account Moves')


class SelectInvoices(Wizard):
    'Select Invoices'
    __name__ = 'account.voucher.select_invoices'

    start_state = 'search_lines'
    search_lines = StateTransition()
    select_lines = StateView('account.voucher.select_invoices.ask',
        'account_voucher_ar.view_search_invoices', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add_lines', 'tryton-ok', default=True),
            ])
    add_lines = StateTransition()

    def transition_search_lines(self):
        Voucher = Pool().get('account.voucher')
        MoveLine = Pool().get('account.move.line')

        voucher = Voucher(Transaction().context.get('active_id'))
        if voucher.voucher_type == 'receipt':
            account_types = ['receivable']
        else:
            account_types = ['payable']
        line_domain = [
            ('party', '=', voucher.party.id),
            ('account.kind', 'in', account_types),
            ('state', '=', 'valid'),
            ('reconciliation', '=', False),
        ]
        self.select_lines.lines = MoveLine.search(line_domain)
        return 'select_lines'

    def default_select_lines(self, fields):
        res = {}
        if self.select_lines.lines:
            res = {'lines': [l.id for l in self.select_lines.lines]}
        return res

    def transition_add_lines(self):
        Voucher = Pool().get('account.voucher')
        VoucherLine = Pool().get('account.voucher.line')

        voucher = Voucher(Transaction().context.get('active_id'))
        total_credit = 0
        total_debit = 0
        move_ids = self.select_lines.lines
        for line in move_ids:
            total_credit += line.credit
            total_debit += line.debit
            if line.credit:
                line_type = 'cr'
                amount = line.credit
            else:
                amount = line.debit
                line_type = 'dr'
            VoucherLine.create([{
                'voucher': Transaction().context.get('active_id'),
                'account': line.account.id,
                'amount_original': amount,
                'amount_unreconciled': amount,
                'line_type': line_type,
                'move_line': line.id,
            }])
        return 'end'
