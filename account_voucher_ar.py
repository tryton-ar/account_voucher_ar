# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
from collections import defaultdict

from trytond.model import Workflow, ModelView, ModelSQL, fields
from trytond.report import Report
from trytond.pool import Pool
from trytond.pyson import Eval, In
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.i18n import gettext

_ZERO = Decimal('0.0')


class AccountVoucherPayMode(ModelSQL, ModelView):
    'Account Voucher Pay Mode'
    __name__ = 'account.voucher.paymode'

    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account',
        domain=[
            ('type', '!=', None),
            ('closed', '!=', True),
            ])


class AccountVoucher(Workflow, ModelSQL, ModelView):
    'Account Voucher'
    __name__ = 'account.voucher'
    _rec_name = 'number'

    _states = {'readonly': In(Eval('state'), ['posted', 'canceled'])}
    _depends = ['state']

    number = fields.Char('Number', readonly=True, help="Voucher Number")
    party = fields.Many2One('party.party', 'Party', required=True,
        states=_states, depends=_depends)
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', select=True, required=True,
        states=_states, depends=_depends)
    pay_lines = fields.One2Many('account.voucher.line.paymode', 'voucher',
        'Pay Mode Lines', states=_states, depends=_depends)
    date = fields.Date('Date', required=True,
        states=_states, depends=_depends)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        states=_states, depends=_depends)
    currency = fields.Many2One('currency.currency', 'Currency', required=True,
        states=_states, depends=_depends)
    currency_code = fields.Function(fields.Char('Currency Code'),
        'on_change_with_currency_code')
    company = fields.Many2One('company.company', 'Company',
        states=_states, depends=_depends)
    lines = fields.One2Many('account.voucher.line', 'voucher', 'Lines',
        states=_states, depends=_depends)
    lines_credits = fields.One2Many('account.voucher.line.credits', 'voucher',
        'Credits', states={
            'invisible': ~Eval('lines_credits'),
            'readonly': In(Eval('state'), ['posted', 'canceled']),
            },
        depends=['lines_credits', 'state'])
    lines_debits = fields.One2Many('account.voucher.line.debits', 'voucher',
        'Debits', states={
            'invisible': ~Eval('lines_debits'),
            'readonly': In(Eval('state'), ['posted', 'canceled']),
            },
        depends=['lines_debits', 'state'])
    comment = fields.Text('Comment', states=_states, depends=_depends)
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
        readonly=True, states={'invisible': ~Eval('move_canceled')},
        depends=['move_canceled'])
    pay_invoice = fields.Many2One('account.invoice', 'Pay Invoice')

    del _states, _depends

    @classmethod
    def __setup__(cls):
        super().__setup__()
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
            raise UserError(gettext(
                'account_voucher_ar.msg_no_voucher_sequence',
                voucher=self.rec_name, fiscalyear=fiscalyear.rec_name))
        self.write([self], {'number': Sequence.get_id(sequence.id)})

    @fields.depends('currency')
    def on_change_with_currency_code(self, name=None):
        if self.currency:
            return self.currency.code

    @fields.depends('party', 'pay_lines', 'lines_credits', 'lines_debits',
        'currency')
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

    @fields.depends('party', 'lines', 'currency')
    def on_change_with_amount_to_pay(self, name=None):
        total = 0
        if self.lines:
            for line in self.lines:
                total += line.amount_unreconciled or _ZERO
        return total

    @fields.depends('party', 'lines', 'currency')
    def on_change_with_amount_invoices(self, name=None):
        total = Decimal('0')
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
        AccountVoucherLineCredits = pool.get('account.voucher.line.credits')
        AccountVoucherLineDebits = pool.get('account.voucher.line.debits')
        AccountVoucherLine = pool.get('account.voucher.line')

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

        clause = [
            ('party', '=', self.party),
            ('state', '=', 'valid'),
            ('reconciliation', '=', None),
            ('move.state', '=', 'posted'),
            ]
        if self.voucher_type == 'receipt':
            clause.append(('account.type.receivable', '=', True))
        else:
            clause.append(('account.type.payable', '=', True))

        if self.pay_invoice:
            move_lines = self.pay_invoice.lines_to_pay
        else:
            move_lines = MoveLine.search(clause)

        for line in move_lines:
            origin = str(line.move_origin)
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
            model = str(line.move_origin)
            invoice_date = None
            if model[:model.find(',')] == 'account.invoice':
                invoice = Invoice(line.move_origin.id)
                invoice_date = invoice.invoice_date
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
            payment_line.date = invoice_date or line.date

            if line.credit and self.voucher_type == 'receipt':
                lines_credits.append(payment_line)
            elif line.debit and self.voucher_type == 'payment':
                lines_debits.append(payment_line)
            else:
                lines.append(payment_line)

        self.lines = sorted(lines, key=lambda x: x.date)
        self.lines_credits = lines_credits
        self.lines_debits = lines_debits

    @classmethod
    def delete(cls, vouchers):
        if not vouchers:
            return True
        for voucher in vouchers:
            if voucher.state != 'draft':
                raise UserError(gettext(
                    'account_voucher_ar.msg_delete_voucher'))
        return super().delete(vouchers)

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
        return super().copy(vouchers, default=default)

    def prepare_move_lines(self):
        pool = Pool()
        Period = pool.get('account.period')
        Move = pool.get('account.move')
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')

        # Check amount
        if not self.amount > _ZERO:
            raise UserError(gettext(
                'account_voucher_ar.msg_missing_pay_lines'))

        move_lines = []
        line_move_ids = []
        move, = Move.create([{
            'period': Period.find(self.company.id, date=self.date),
            'journal': self.journal.id,
            'date': self.date,
            'origin': str(self),
            }])
        self.write([self], {'move': move.id})

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
                    'party': (line.pay_mode.account.party_required and
                        self.party.id or None),
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
                    'party': (line.account.party_required and
                        self.party.id or None),
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
                    'party': (line.account.party_required and
                        self.party.id or None),
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
                    raise UserError(gettext(
                        'account_voucher_ar.msg_amount_greater_unreconciled'))

                origin = str(line.move_line.move_origin)
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
                    description = Invoice(line.move_line.move_origin.id).number
                else:
                    debit = amount
                    credit = _ZERO
                    description = Invoice(
                        line.move_line.move_origin.id).reference

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
                    'party': (line.account.party_required and
                        self.party.id or None),
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
                account = self.party.account_receivable_used
                party_required = account.party_required
            else:
                debit = amount
                credit = _ZERO
                account = self.party.account_payable_used
                party_required = account.party_required

            if self.voucher_type == 'receipt' and second_currency:
                amount_second_currency *= -1

            move_lines.append({
                'description': self.number,
                'debit': debit,
                'credit': credit,
                'account': account.id,
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

        lines_to_reconcile = defaultdict(list)
        # reconcile check
        for line in self.lines:
            origin = str(line.move_line.move_origin)
            origin = origin[:origin.find(',')]
            if origin not in ['account.invoice',
                    'account.voucher']:
                continue
            if line.amount == _ZERO:
                continue
            invoice = Invoice(line.move_line.move_origin.id)

            with Transaction().set_context(date=self.date):
                amount = Currency.compute(self.currency,
                    line.amount, self.company.currency)

            if self.voucher_type == 'payment':
                amount = -amount
            reconcile_lines, remainder = \
                Invoice.get_reconcile_lines_for_amount(
                    invoice, amount)
            if remainder == _ZERO:
                for reconcile_line in reconcile_lines:
                    lines_to_reconcile[line.account.id].append(
                        reconcile_line.id)
            for move_line in created_lines:
                if move_line.description == 'advance':
                    continue
                if (move_line.debit != abs(amount) and
                        move_line.credit != abs(amount)):
                    continue
                invoice_number = invoice.reference
                if invoice.type == 'out':
                    invoice_number = invoice.number
                if move_line.description == invoice_number:
                    if remainder == _ZERO:
                        lines_to_reconcile[move_line.account.id].append(
                            move_line.id)
                    Invoice.write([invoice], {
                        'payment_lines': [('add', [move_line.id])],
                        })
        if lines_to_reconcile:
            for lines_ids in lines_to_reconcile.values():
                lines = MoveLine.browse(list(set(lines_ids)))
                MoveLine.reconcile(lines)

        reconcile_lines = []
        if self.lines_credits:
            for line in self.lines_credits:
                reconcile_lines.append(line.move_line)
            for move_line in created_lines:
                if move_line.description == 'advance':
                    reconcile_lines.append(move_line)
        if reconcile_lines:
            MoveLine.reconcile(reconcile_lines)

        reconcile_lines = []
        if self.lines_debits:
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

        reconciliations = [x.reconciliation for x in self.move.lines
                if x.reconciliation]
        with Transaction().set_user(0, set_context=True):
            if reconciliations:
                Reconciliation.delete(reconciliations)

        Invoice().remove_payment_lines(self.move.lines)

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

        lines_to_reconcile = defaultdict(list)
        for line in self.move.lines:
            if line.account.reconcile:
                lines_to_reconcile[line.account.id].append(line)
        for cancel_line in canceled_move.lines:
            if cancel_line.account.reconcile:
                lines_to_reconcile[cancel_line.account.id].append(cancel_line)

        for lines in list(lines_to_reconcile.values()):
            MoveLine.reconcile(lines)

        return True

    @classmethod
    def check_already_reconciled(cls, vouchers):
        reconciled_lines = []
        for voucher in vouchers:
            reconciled_lines = [l.name for l in voucher.lines
                if l.move_line.reconciliation]
            if reconciled_lines:
                raise UserError(gettext(
                    'account_voucher_ar.msg_post_already_reconciled',
                    lines='\n'.join(reconciled_lines)))

    @classmethod
    def check_amount_invoices(cls, vouchers):
        for voucher in vouchers:
            if voucher.amount_invoices > voucher.amount:
                raise UserError(gettext(
                    'account_voucher_ar.msg_amount_invoices_greater_amount'))

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

    _states = {'readonly': True}

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE', select=True)
    reference = fields.Function(fields.Char('reference'),
        'get_reference')
    name = fields.Char('Name', states=_states)
    account = fields.Many2One('account.account', 'Account',
        domain=[
            ('type', '!=', None),
            ('closed', '!=', True),
            ])
    amount = fields.Numeric('Amount', digits=(16, 2))
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True)
    move_line = fields.Many2One('account.move.line', 'Move Line')
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)
    date_expire = fields.Function(fields.Date('Expire date'),
        'get_expire_date')

    del _states

    def get_reference(self, name):
        Invoice = Pool().get('account.invoice')

        if self.move_line.move:
            invoices = Invoice.search([
                ('move', '=', self.move_line.move.id)])
            if invoices:
                return invoices[0].reference

    def get_expire_date(self, name):
        if self.move_line:
            return self.move_line.maturity_date


class AccountVoucherLineCredits(ModelSQL, ModelView):
    'Account Voucher Line Credits'
    __name__ = 'account.voucher.line.credits'

    _states = {'readonly': True}

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE', select=True)
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account',
        domain=[
            ('type', '!=', None),
            ('closed', '!=', True),
            ],
        states=_states)
    amount = fields.Numeric('Amount', digits=(16, 2),
        states=_states)
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True, states=_states)
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states=_states)
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)

    del _states


class AccountVoucherLineDebits(ModelSQL, ModelView):
    'Account Voucher Line Debits'
    __name__ = 'account.voucher.line.debits'

    _states = {'readonly': True}

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE', select=True)
    name = fields.Char('Name')
    account = fields.Many2One('account.account', 'Account',
        domain=[
            ('type', '!=', None),
            ('closed', '!=', True),
            ],
        states=_states)
    amount = fields.Numeric('Amount', digits=(16, 2),
        states=_states)
    line_type = fields.Selection([
        ('cr', 'Credit'),
        ('dr', 'Debit'),
        ], 'Type', select=True, states=_states)
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states=_states)
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)

    del _states


class AccountVoucherLinePaymode(ModelSQL, ModelView):
    'Account Voucher Line Pay Mode'
    __name__ = 'account.voucher.line.paymode'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    pay_mode = fields.Many2One('account.voucher.paymode', 'Pay Mode',
        required=True)
    pay_amount = fields.Numeric('Pay Amount', digits=(16, 2), required=True)


class AccountVoucherReport(Report):
    __name__ = 'account.voucher'

    @classmethod
    def get_context(cls, records, data):
        report_context = super().get_context(records, data)
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
