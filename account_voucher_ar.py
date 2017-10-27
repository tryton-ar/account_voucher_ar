# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import Workflow, ModelView, ModelSQL, fields
from trytond.transaction import Transaction
from trytond.pyson import Eval, In
from trytond.pool import Pool, PoolMeta
from trytond.report import Report

__all__ = ['FiscalYear', 'AccountVoucherPayMode', 'AccountVoucher',
    'AccountVoucherLine', 'AccountVoucherLineCredits',
    'AccountVoucherLineDebits', 'AccountVoucherLinePaymode',
    'AccountVoucherReport']

_STATES = {
    'readonly': In(Eval('state'), ['posted', 'canceled']),
    }
_DEPENDS = ['state']

_ZERO = Decimal('0.0')


class FiscalYear:
    __name__ = 'account.fiscalyear'
    __metaclass__ = PoolMeta

    payment_sequence = fields.Many2One('ir.sequence',
        'Payment Sequence', required=True,
        domain=[
            ('code', '=', 'account.voucher.payment'),
                ['OR',
                    ('company', '=', Eval('company')),
                    ('company', '=', None)
                ]],
            context={
                'code': 'account.voucher.payment',
                'company': Eval('company'),
            },
            depends=['company'])
    receipt_sequence = fields.Many2One('ir.sequence',
        'Receipt Sequence', required=True,
        domain=[
            ('code', '=', 'account.voucher.receipt'),
                ['OR',
                    ('company', '=', Eval('company')),
                    ('company', '=', None)
                ]],
            context={
                'code': 'account.voucher.receipt',
                'company': Eval('company'),
            },
            depends=['company'])

    @classmethod
    def __setup__(cls):
        super(FiscalYear, cls).__setup__()
        cls._error_messages.update({
                'change_voucher_sequence': ('You can not change '
                    'voucher sequence in fiscal year "%s" because there are '
                    'already posted vouchers in this fiscal year.'),
                'different_voucher_sequence': ('Fiscal year "%(first)s" and '
                    '"%(second)s" have the same voucher sequence.'),
                })

    @classmethod
    def validate(cls, years):
        super(FiscalYear, cls).validate(years)
        for year in years:
            year.check_voucher_sequences()

    def check_voucher_sequences(self):
        for sequence in ('payment_sequence', 'receipt_sequence'):
            fiscalyears = self.search([
                    (sequence, '=', getattr(self, sequence).id),
                    ('id', '!=', self.id),
                    ])
            if fiscalyears:
                self.raise_user_error('different_voucher_sequence', {
                        'first': self.rec_name,
                        'second': fiscalyears[0].rec_name,
                        })

    @classmethod
    def write(cls, *args):
        Voucher = Pool().get('account.voucher')

        actions = iter(args)
        for fiscalyears, values in zip(actions, actions):
            for sequence in ('payment_sequence', 'receipt_sequence'):
                    if not values.get(sequence):
                        continue
                    for fiscalyear in fiscalyears:
                        if (getattr(fiscalyear, sequence)
                                and (getattr(fiscalyear, sequence).id !=
                                    values[sequence])):
                            if Voucher.search([
                                        ('date', '>=', fiscalyear.start_date),
                                        ('date', '<=', fiscalyear.end_date),
                                        ('number', '!=', None),
                                        ('voucher_type', '=', sequence[:-9]),
                                        ]):
                                cls.raise_user_error('change_voucher_sequence',
                                    (fiscalyear.rec_name,))
        super(FiscalYear, cls).write(*args)

    def get_voucher_sequence(self, voucher_type):
        return getattr(self, voucher_type + '_sequence')


class AccountVoucherPayMode(ModelSQL, ModelView):
    'Account Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'

    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account')


class AccountVoucher(Workflow, ModelSQL, ModelView):
    'Account Voucher'
    __name__ = 'account.voucher'
    _rec_name = 'number'

    number = fields.Char('Number', readonly=True, help="Voucher Number")
    party = fields.Many2One('party.party', 'Party', required=True,
        states=_STATES, depends=_DEPENDS)
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', select=True, required=True, states=_STATES,
        depends=_DEPENDS)
    pay_lines = fields.One2Many('account.voucher.line.paymode', 'voucher',
        'Pay Mode Lines', states=_STATES, depends=_DEPENDS)
    date = fields.Date('Date', required=True, states=_STATES, depends=_DEPENDS)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        states=_STATES, depends=_DEPENDS)
    currency = fields.Many2One('currency.currency', 'Currency', required=True,
        states=_STATES, depends=_DEPENDS)
    currency_code = fields.Function(fields.Char('Currency Code'),
        'on_change_with_currency_code')
    company = fields.Many2One('company.company', 'Company',
        states=_STATES, depends=_DEPENDS)
    lines = fields.One2Many('account.voucher.line', 'voucher', 'Lines',
        states=_STATES, depends=_DEPENDS)
    lines_credits = fields.One2Many('account.voucher.line.credits', 'voucher',
        'Credits', states={
            'invisible': ~Eval('lines_credits'),
            'readonly': In(Eval('state'), ['posted', 'canceled']),
            }, depends=['state'])
    lines_debits = fields.One2Many('account.voucher.line.debits', 'voucher',
        'Debits', states={
            'invisible': ~Eval('lines_debits'),
            'readonly': In(Eval('state'), ['posted', 'canceled']),
            }, depends=['state'])
    comment = fields.Text('Comment', states=_STATES, depends=_DEPENDS)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('canceled', 'Canceled'),
        ], 'State', select=True, readonly=True)
    amount = fields.Function(fields.Numeric('Payment', digits=(16, 2)),
        'on_change_with_amount')
    amount_to_pay = fields.Function(fields.Numeric('To Pay', digits=(16, 2)),
        'on_change_with_amount_to_pay')
    amount_invoices = fields.Function(fields.Numeric('Invoices',
        digits=(16, 2)), 'on_change_with_amount_invoices')
    move = fields.Many2One('account.move', 'Move', readonly=True)
    move_canceled = fields.Many2One('account.move', 'Move Canceled',
        readonly=True, states={
            'invisible': ~Eval('move_canceled'),
            })
    pay_invoice = fields.Many2One('account.invoice', 'Pay Invoice')

    @classmethod
    def __setup__(cls):
        super(AccountVoucher, cls).__setup__()
        cls._error_messages.update({
            'missing_pay_lines': 'You have to enter pay mode lines!',
            'amount_greater_unreconciled': 'Amount greater than invoice '
                'amount',
            'delete_voucher': 'You can not delete a voucher that is posted!',
            'post_already_reconciled': 'You can not post the voucher because '
                'it already has reconciled lines!\n\nLines:\n%s',
            'amount_invoices_greater_amount': ('You can not post the voucher '
                'because Invoices amount is greater than Payment amount'),
        })
        cls._transitions |= set((
                ('draft', 'posted'),
                ('posted', 'canceled'),
                ))
        cls._buttons.update({
                'post': {
                    'invisible': Eval('state') != 'draft',
                    },
                'cancel': {
                    'invisible': Eval('state') != 'posted',
                    },
                })
        cls._order.insert(0, ('date', 'DESC'))
        cls._order.insert(1, ('number', 'DESC'))

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_date():
        Date = Pool().get('ir.date')
        return Date.today()

    def set_number(self):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        FiscalYear = pool.get('account.fiscalyear')

        fiscalyear_id = FiscalYear.find(self.company.id,
            date=self.date)
        fiscalyear = FiscalYear(fiscalyear_id)
        sequence = fiscalyear.get_voucher_sequence(self.voucher_type)
        if not sequence:
            self.raise_user_error('no_voucher_sequence', {
                    'voucher': self.rec_name,
                    'fiscalyear': fiscalyear.rec_name,
                    })
        self.write([self], {'number': Sequence.get_id(sequence.id)})

    @fields.depends('currency')
    def on_change_with_currency_code(self, name=None):
        if self.currency:
            return self.currency.code

    @fields.depends('party', 'pay_lines', 'lines_credits', 'lines_debits')
    def on_change_with_amount(self, name=None):
        amount = _ZERO
        if self.pay_lines:
            for line in self.pay_lines:
                if line.pay_amount:
                    amount += line.pay_amount
        if self.lines_credits:
            for line in self.lines_credits:
                if line.amount_original:
                    amount += line.amount_original
        if self.lines_debits:
            for line in self.lines_debits:
                if line.amount_original:
                    amount += line.amount_original
        return amount

    @fields.depends('party', 'lines')
    def on_change_with_amount_to_pay(self, name=None):
        total = 0
        if self.lines:
            for line in self.lines:
                total += line.amount_unreconciled or _ZERO
        return total

    @fields.depends('lines')
    def on_change_with_amount_invoices(self, name=None):
        total = 0
        if self.lines:
            for line in self.lines:
                total += line.amount or _ZERO
        return total

    @fields.depends('party', 'voucher_type', 'lines', 'lines_credits',
        'lines_debits', 'currency', 'company', 'date', 'pay_invoice')
    def on_change_party(self):
        self.add_lines()

    @fields.depends('party', 'voucher_type', 'lines', 'lines_credits',
        'lines_debits', 'currency', 'company', 'date', 'pay_invoice')
    def on_change_currency(self):
        self.add_lines()

    def add_lines(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')
        InvoiceAccountMoveLine = pool.get('account.invoice-account.move.line')
        Currency = pool.get('currency.currency')

        lines = []
        lines_credits = []
        lines_debits = []

        if not self.currency or not self.party:
            self.lines = lines
            self.lines_credits = lines_credits
            self.lines_debits = lines_debits
            return

        if self.lines:
            return

        second_currency = None
        if self.currency != self.company.currency:
            second_currency = self.currency

        if self.voucher_type == 'receipt':
            account_types = ['receivable']
        else:
            account_types = ['payable']

        if self.pay_invoice:
            move_lines = self.pay_invoice.lines_to_pay
        else:
            move_lines = MoveLine.search([
                    ('party', '=', self.party),
                    ('account.kind', 'in', account_types),
                    ('state', '=', 'valid'),
                    ('reconciliation', '=', None),
                    ('move.state', '=', 'posted'),
                    ])

        for line in move_lines:
            origin = str(line.origin)
            origin = origin[:origin.find(',')]
            if origin not in ['account.invoice', 'account.voucher']:
                continue

            invoice = InvoiceAccountMoveLine.search([
                ('line', '=', line.id),
            ])
            if invoice:
                continue

            if line.credit:
                line_type = 'cr'
                amount = line.credit
            else:
                amount = line.debit
                line_type = 'dr'

            amount_residual = abs(line.amount_residual)
            if second_currency:
                with Transaction().set_context(date=self.date):
                    amount = Currency.compute(self.company.currency,
                        amount, self.currency)
                    amount_residual = Currency.compute(self.company.currency,
                        amount_residual, self.currency)

            name = ''
            model = str(line.origin)
            if model[:model.find(',')] == 'account.invoice':
                invoice = Invoice(line.origin.id)
                if invoice.type[0:3] == 'out':
                    name = invoice.number
                else:
                    name = invoice.reference

            if line.credit and self.voucher_type == 'receipt':
                payment_line = AccountVoucherLineCredits()
            elif line.debit and self.voucher_type == 'payment':
                payment_line = AccountVoucherLineDebits()
            else:
                payment_line = AccountVoucherLine()
            payment_line.name = name
            payment_line.account = line.account.id
            payment_line.amount = _ZERO
            payment_line.amount_original = amount
            payment_line.amount_unreconciled = amount_residual
            payment_line.line_type = line_type
            payment_line.move_line = line.id
            payment_line.date = line.date
            payment_line.date_expire = line.maturity_date

            if line.credit and self.voucher_type == 'receipt':
                lines_credits.append(payment_line)
            elif line.debit and self.voucher_type == 'payment':
                lines_debits.append(payment_line)
            else:
                lines.append(payment_line)

        self.lines = lines
        self.lines_credits = lines_credits
        self.lines_debits = lines_debits

    @classmethod
    def delete(cls, vouchers):
        if not vouchers:
            return True
        for voucher in vouchers:
            if voucher.state != 'draft':
                cls.raise_user_error('delete_voucher')
        return super(AccountVoucher, cls).delete(vouchers)

    @classmethod
    def copy(cls, vouchers, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['number'] = None
        default['date'] = cls.default_date()
        default['state'] = cls.default_state()
        default['lines'] = None
        default['lines_credits'] = None
        default['lines_debits'] = None
        default['move'] = None
        default['move_canceled'] = None

        return super(AccountVoucher, cls).copy(vouchers, default=default)

    def prepare_move_lines(self):
        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')

        # Check amount
        if not self.amount > _ZERO:
            self.raise_user_error('missing_pay_lines')

        move_lines = []
        line_move_ids = []
        move, = Move.create([{
            'period': Period.find(self.company.id, date=self.date),
            'journal': self.journal.id,
            'date': self.date,
            'origin': str(self),
        }])
        self.write([self], {
                'move': move.id,
                })

        second_currency = None
        if self.currency != self.company.currency:
            second_currency = self.currency.id

        #
        # Pay Modes
        #
        if self.pay_lines:
            for line in self.pay_lines:
                amount = line.pay_amount
                amount_second_currency = None
                if second_currency:
                    amount_second_currency = amount
                    with Transaction().set_context(date=self.date):
                        amount = Currency.compute(self.currency,
                            amount, self.company.currency)

                if self.voucher_type == 'receipt':
                    if amount < _ZERO:
                        debit = _ZERO
                        credit = amount * -1
                    else:
                        debit = amount
                        credit = _ZERO
                else:
                    if amount < _ZERO:
                        debit = amount * -1
                        credit = _ZERO
                    else:
                        debit = _ZERO
                        credit = amount

                if self.voucher_type == 'payment' and second_currency:
                    amount_second_currency *= -1
                if second_currency and amount < _ZERO:
                    amount_second_currency *= -1

                move_lines.append({
                    'debit': debit,
                    'credit': credit,
                    'account': line.pay_mode.account.id,
                    'move': move.id,
                    'journal': self.journal.id,
                    'period': Period.find(self.company.id, date=self.date),
                    'party': (line.pay_mode.account.party_required
                        and self.party.id or None),
                    'amount_second_currency': amount_second_currency,
                    'second_currency': second_currency,
                })

        #
        # Credits
        #
        if self.lines_credits:
            for line in self.lines_credits:
                amount = line.amount_original
                amount_second_currency = None
                if second_currency:
                    amount_second_currency = amount
                    with Transaction().set_context(date=self.date):
                        amount = Currency.compute(self.currency,
                            amount, self.company.currency)

                debit = amount
                credit = _ZERO

                if self.voucher_type == 'payment' and second_currency:
                    amount_second_currency *= -1

                move_lines.append({
                    'description': 'advance',
                    'debit': debit,
                    'credit': credit,
                    'account': line.account.id,
                    'move': move.id,
                    'journal': self.journal.id,
                    'period': Period.find(self.company.id, date=self.date),
                    'date': self.date,
                    'maturity_date': self.date,
                    'party': (line.account.party_required
                        and self.party.id or None),
                    'amount_second_currency': amount_second_currency,
                    'second_currency': second_currency,
                })

        #
        # Debits
        #
        if self.lines_debits:
            for line in self.lines_debits:
                amount = line.amount_original
                amount_second_currency = None
                if second_currency:
                    amount_second_currency = amount
                    with Transaction().set_context(date=self.date):
                        amount = Currency.compute(self.currency,
                            amount, self.company.currency)

                debit = _ZERO
                credit = amount

                if self.voucher_type == 'payment' and second_currency:
                    amount_second_currency *= -1

                move_lines.append({
                    'description': 'advance',
                    'debit': debit,
                    'credit': credit,
                    'account': line.account.id,
                    'move': move.id,
                    'journal': self.journal.id,
                    'period': Period.find(self.company.id, date=self.date),
                    'date': self.date,
                    'maturity_date': self.date,
                    'party': (line.account.party_required
                        and self.party.id or None),
                    'amount_second_currency': amount_second_currency,
                    'second_currency': second_currency,
                })

        #
        # Voucher Lines
        #
        with Transaction().set_context(date=self.date):
            total = Currency.compute(self.currency,
                self.amount, self.company.currency)
        invoices = 'Factura/s: '
        if self.lines:
            for line in self.lines:
                if line.amount > line.amount_unreconciled:
                    self.raise_user_error('amount_greater_unreconciled')

                origin = str(line.move_line.origin)
                origin = origin[:origin.find(',')]
                if origin not in ('account.invoice', 'account.voucher'):
                    continue
                if not line.amount:
                    continue

                amount = line.amount
                amount_second_currency = None
                if second_currency:
                    amount_second_currency = amount
                    with Transaction().set_context(date=self.date):
                        amount = Currency.compute(self.currency,
                            amount, self.company.currency)

                line_move_ids.append(line.move_line)
                if self.voucher_type == 'receipt':
                    debit = _ZERO
                    credit = amount
                    description = Invoice(line.move_line.origin.id).number
                else:
                    debit = amount
                    credit = _ZERO
                    description = Invoice(line.move_line.origin.id).reference

                if self.voucher_type == 'receipt' and second_currency:
                    amount_second_currency *= -1

                total -= amount
                invoices += description + ', ' if description else ', '
                move_lines.append({
                    'description': description,
                    'debit': debit,
                    'credit': credit,
                    'account': line.account.id,
                    'move': move.id,
                    'journal': self.journal.id,
                    'period': Period.find(self.company.id, date=self.date),
                    'date': self.date,
                    'maturity_date': self.date,
                    'party': (line.account.party_required
                        and self.party.id or None),
                    'amount_second_currency': amount_second_currency,
                    'second_currency': second_currency,
                })

        if total != _ZERO:
            amount = total
            amount_second_currency = None
            if second_currency:
                with Transaction().set_context(date=self.date):
                    amount_second_currency = Currency.compute(
                        self.company.currency, amount, self.currency)

            if self.voucher_type == 'receipt':
                debit = _ZERO
                credit = amount
                account_id = self.party.account_receivable.id
                party_required = self.party.account_receivable.party_required
            else:
                debit = amount
                credit = _ZERO
                account_id = self.party.account_payable.id
                party_required = self.party.account_payable.party_required

            if self.voucher_type == 'receipt' and second_currency:
                amount_second_currency *= -1

            move_lines.append({
                'description': self.number,
                'debit': debit,
                'credit': credit,
                'account': account_id,
                'move': move.id,
                'journal': self.journal.id,
                'period': Period.find(self.company.id, date=self.date),
                'date': self.date,
                'maturity_date': self.date,
                'party': party_required and self.party.id or None,
                'amount_second_currency': amount_second_currency,
                'second_currency': second_currency,
            })

        Move.write([move], {'description': invoices[:-2]})

        return move_lines

    def create_move(self, move_lines):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')

        created_lines = MoveLine.create(move_lines)
        Move.post([self.move])

        lines_to_reconcile = []
        total_remainder = _ZERO
        # reconcile check
        for line in self.lines:
            origin = str(line.move_line.origin)
            origin = origin[:origin.find(',')]
            if origin not in ['account.invoice',
                    'account.voucher']:
                continue
            if line.amount == _ZERO:
                continue
            invoice = Invoice(line.move_line.origin.id)

            with Transaction().set_context(date=self.date):
                amount = Currency.compute(self.currency,
                    line.amount, self.company.currency)

            if self.voucher_type == 'payment':
                amount = -amount
            reconcile_lines, remainder = \
                Invoice.get_reconcile_lines_for_amount(
                    invoice, amount)
            lines_to_reconcile.extend(reconcile_lines)
            total_remainder += remainder
            for move_line in created_lines:
                if move_line.description == 'advance':
                    continue
                if invoice.type[:2] == 'in':
                    reference = invoice.reference
                else:
                    reference = invoice.number
                if move_line.description == reference:
                    if move_line not in lines_to_reconcile:
                        lines_to_reconcile.append(move_line)
                    Invoice.write([invoice], {
                        'payment_lines': [('add', [move_line.id])],
                        })
        if total_remainder == _ZERO:
            lines_to_reconcile = list(set(lines_to_reconcile))
            if lines_to_reconcile:
                MoveLine.reconcile(lines_to_reconcile)

        reconcile_lines = []
        for line in self.lines_credits:
            reconcile_lines.append(line.move_line)
            for move_line in created_lines:
                if move_line.description == 'advance':
                    reconcile_lines.append(move_line)
        if reconcile_lines:
            MoveLine.reconcile(reconcile_lines)

        reconcile_lines = []
        for line in self.lines_debits:
            reconcile_lines.append(line.move_line)
            for move_line in created_lines:
                if move_line.description == 'advance':
                    reconcile_lines.append(move_line)
        if reconcile_lines:
            MoveLine.reconcile(reconcile_lines)

        return True

    def create_cancel_move(self):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Period = pool.get('account.period')
        Reconciliation = pool.get('account.move.reconciliation')
        Invoice = pool.get('account.invoice')

        canceled_move, = Move.copy([self.move], {
                'period': Period.find(self.company.id, date=self.move.date),
                'date': self.move.date,
                })
        self.write([self], {
                'move_canceled': canceled_move.id,
                })

        for line in canceled_move.lines:
            aux = line.debit
            line.debit = line.credit
            line.credit = aux
            line.amount_second_currency = (line.amount_second_currency * -1 if
                line.amount_second_currency else _ZERO)
            line.save()

        Move.post([self.move_canceled])

        reconciliations = [x.reconciliation for x in self.move.lines
                if x.reconciliation]
        with Transaction().set_user(0, set_context=True):
            if reconciliations:
                Reconciliation.delete(reconciliations)

        for line in self.lines:
            origin = str(line.move_line.origin)
            origin = origin[:origin.find(',')]
            if origin not in ['account.invoice',
                    'account.voucher']:
                continue
            if line.amount == _ZERO:
                continue
            invoice = Invoice(line.move_line.origin.id)
            for move_line in self.move_canceled.lines:
                if move_line.description == 'advance':
                    continue
                invoice_number = invoice.reference
                if invoice.type == 'out':
                    invoice_number = invoice.number
                if move_line.description == invoice_number:
                    Invoice.write([invoice], {
                        'payment_lines': [('add', [move_line.id])],
                        })

        lines_to_reconcile = []
        for line in self.move.lines:
            if line.account.reconcile:
                lines_to_reconcile.append(line)
        for cancel_line in canceled_move.lines:
            if cancel_line.account.reconcile:
                lines_to_reconcile.append(cancel_line)

        if lines_to_reconcile:
            MoveLine.reconcile(lines_to_reconcile)

        return True

    @classmethod
    def check_already_reconciled(cls, vouchers):
        reconciled_lines = []
        for voucher in vouchers:
            reconciled_lines = [l.name for l in voucher.lines
                                if l.move_line.reconciliation]
            if reconciled_lines:
                cls.raise_user_error('post_already_reconciled',
                                     ('\n'.join(reconciled_lines),))

    @classmethod
    def check_amount_invoices(cls, vouchers):
        for voucher in vouchers:
            if voucher.amount_invoices > voucher.amount:
                cls.raise_user_error('amount_invoices_greater_amount')

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, vouchers):
        cls.check_already_reconciled(vouchers)
        cls.check_amount_invoices(vouchers)
        for voucher in vouchers:
            voucher.set_number()
            move_lines = voucher.prepare_move_lines()
            voucher.create_move(move_lines)

    @classmethod
    @ModelView.button
    @Workflow.transition('canceled')
    def cancel(cls, vouchers):
        for voucher in vouchers:
            voucher.create_cancel_move()


class AccountVoucherLine(ModelSQL, ModelView):
    'Account Voucher Line'
    __name__ = 'account.voucher.line'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    reference = fields.Function(fields.Char('reference',),
        'get_reference')
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account')
    amount = fields.Numeric('Amount', digits=(16, 2))
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True)
    move_line = fields.Many2One('account.move.line', 'Move Line')
    amount_original = fields.Numeric('Original Amount', digits=(16, 2),
        states={'readonly': True})
    amount_unreconciled = fields.Numeric('Unreconciled amount', digits=(16, 2),
        states={'readonly': True})
    date = fields.Date('Date')
    date_expire = fields.Function(fields.Date('Expire date'),
            'get_expire_date')

    def get_reference(self, name):
        Invoice = Pool().get('account.invoice')

        if self.move_line.move:
            invoices = Invoice.search(
                [('move', '=', self.move_line.move.id)])
            if invoices:
                return invoices[0].reference

    def get_expire_date(self, name):
        if self.move_line:
            return self.move_line.maturity_date


class AccountVoucherLineCredits(ModelSQL, ModelView):
    'Account Voucher Line Credits'
    __name__ = 'account.voucher.line.credits'

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE', select=True)
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account',
        states={'readonly': True})
    amount = fields.Numeric('Amount', digits=(16, 2),
        states={'readonly': True})
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True, states={'readonly': True})
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states={'readonly': True})
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states={'readonly': True})
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states={'readonly': True})
    date = fields.Date('Date', states={'readonly': True})


class AccountVoucherLineDebits(ModelSQL, ModelView):
    'Account Voucher Line Debits'
    __name__ = 'account.voucher.line.debits'

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE', select=True)
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account',
        states={'readonly': True})
    amount = fields.Numeric('Amount', digits=(16, 2),
        states={'readonly': True})
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True, states={'readonly': True})
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states={'readonly': True})
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states={'readonly': True})
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states={'readonly': True})
    date = fields.Date('Date', states={'readonly': True})


class AccountVoucherLinePaymode(ModelSQL, ModelView):
    'Account Voucher Line Pay Mode'
    __name__ = 'account.voucher.line.paymode'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    pay_mode = fields.Many2One('account.voucher.paymode', 'Pay Mode',
        required=True, states=_STATES)
    pay_amount = fields.Numeric('Pay Amount', digits=(16, 2), required=True,
        states=_STATES)


class AccountVoucherReport(Report):
    __name__ = 'account.voucher'

    @classmethod
    def get_context(cls, records, data):
        report_context = super(AccountVoucherReport, cls).get_context(records,
            data)
        report_context['company'] = report_context['user'].company
        report_context['compute_currency'] = cls.compute_currency
        report_context['format_vat_number'] = cls.format_vat_number
        report_context['get_iva_condition'] = cls.get_iva_condition
        return report_context

    @classmethod
    def compute_currency(cls, voucher_currency, amount_original,
            company_currency):
        return voucher_currency.compute(company_currency, amount_original,
            voucher_currency)

    @classmethod
    def format_vat_number(cls, vat_number=''):
        return '%s-%s-%s' % (vat_number[:2], vat_number[2:-1], vat_number[-1])

    @classmethod
    def get_iva_condition(cls, party):
        return dict(party._fields['iva_condition'].selection)[
            party.iva_condition]
