# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
from collections import defaultdict, namedtuple
from itertools import combinations

from trytond.model import Workflow, ModelView, ModelSQL, fields, Index
from trytond.report import Report
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, In, If, Bool
from trytond.tools import grouped_slice
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

    _states = {'readonly': Eval('state') != 'draft'}
    _states_done = {'readonly': In(Eval('state'), ['posted', 'cancelled'])}

    number = fields.Char('Number', readonly=True, help="Voucher Number")
    party = fields.Many2One('party.party', 'Party', required=True,
        context={'company': Eval('company', -1)},
        states=_states, depends={'company'})
    voucher_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ], 'Type', required=True, states=_states)
    pay_lines = fields.One2Many('account.voucher.line.paymode', 'voucher',
        'Pay Mode Lines', states=_states_done)
    date = fields.Date('Date', required=True, states=_states)
    journal = fields.Many2One('account.journal', 'Journal', required=True,
        context={'company': Eval('company', -1)},
        states=_states, depends={'company'})
    currency = fields.Many2One('currency.currency', 'Currency', required=True,
        states=_states)
    currency_rate = fields.Numeric('Currency rate', digits=(12, 6),
        states=_states_done)
    currency_code = fields.Function(fields.Char('Currency Code'),
        'on_change_with_currency_code')
    company = fields.Many2One('company.company', 'Company', states=_states)
    lines = fields.One2Many('account.voucher.line', 'voucher', 'Lines',
        states=_states)
    lines_credits = fields.One2Many('account.voucher.line.credits', 'voucher',
        'Credits', states={
            'invisible': ~Eval('lines_credits'),
            'readonly': In(Eval('state'), ['posted', 'cancelled']),
            })
    lines_debits = fields.One2Many('account.voucher.line.debits', 'voucher',
        'Debits', states={
            'invisible': ~Eval('lines_debits'),
            'readonly': In(Eval('state'), ['posted', 'cancelled']),
            })
    comment = fields.Text('Comment', states=_states_done)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
        ], 'State', readonly=True)
    amount = fields.Function(fields.Numeric('Payment', digits=(16, 2)),
        'on_change_with_amount')
    amount_to_pay = fields.Function(fields.Numeric('To Pay', digits=(16, 2)),
        'on_change_with_amount_to_pay')
    amount_invoices = fields.Function(fields.Numeric('Invoices',
        digits=(16, 2)), 'on_change_with_amount_invoices')
    move = fields.Many2One('account.move', 'Move', readonly=True)
    move_cancelled = fields.Many2One('account.move', 'Move Cancelled',
        readonly=True, states={'invisible': ~Eval('move_cancelled')})
    pay_invoice = fields.Many2One('account.invoice', 'Pay Invoice')

    del _states

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._transitions |= set((
            ('draft', 'posted'),
            ('posted', 'cancelled'),
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
        t = cls.__table__()
        #cls._sql_indexes.update({
            #Index(t, (t.state, Index.Equality())),
            #})

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
        table_h = cls.__table_handler__(module_name)
        sql_table = cls.__table__()
        super().__register__(module_name)
        cursor.execute(*sql_table.update(
            [sql_table.state], ['cancelled'],
            where=sql_table.state == 'canceled'))
        if table_h.column_exist('move_canceled'):
            cursor.execute(*sql_table.update(
                [sql_table.move_cancelled], [sql_table.move_canceled]))
            table_h.drop_column('move_canceled')

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
        FiscalYear = pool.get('account.fiscalyear')

        fiscalyear_id = FiscalYear.find(self.company.id,
            date=self.date)
        fiscalyear = FiscalYear(fiscalyear_id)
        sequence = fiscalyear.get_voucher_sequence(self.voucher_type)
        if not sequence:
            raise UserError(gettext(
                'account_voucher_ar.msg_no_voucher_sequence',
                voucher=self.rec_name, fiscalyear=fiscalyear.rec_name))
        self.write([self], {'number': sequence.get()})

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

    @fields.depends('lines', 'currency', 'company')
    def on_change_with_currency_rate(self, name=None):
        if (not self.currency or not self.company or
                self.currency == self.company.currency):
            return None
        if not self.lines:
            return None
        amount, amount_second_currency = Decimal(0), Decimal(0)
        for line in self.lines:
            amount += ((line.move_line.credit or _ZERO) +
                (line.move_line.debit or _ZERO))
            amount_second_currency += (line.move_line.amount_second_currency
                and abs(line.move_line.amount_second_currency) or _ZERO)
        if not amount or not amount_second_currency:
            return None
        return Decimal(amount / amount_second_currency).quantize(
            Decimal(str(10 ** -6)))

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
            if origin not in [
                    'account.invoice',
                    'account.voucher',
                    'account.statement']:
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
            currency_rate = None
            if second_currency:
                if line.second_currency == self.currency:
                    currency_rate = Decimal(
                        amount / abs(line.amount_second_currency)).quantize(
                        Decimal(str(10 ** -6)))
                with Transaction().set_context(
                        currency_rate=currency_rate, date=self.date):
                    amount = Currency.compute(
                        self.company.currency, amount,
                        self.currency)
                    amount_residual = Currency.compute(
                        self.company.currency, amount_residual,
                        self.currency)

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
            payment_line.currency_rate = currency_rate

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
        default['move_cancelled'] = None
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
                    with Transaction().set_context(
                            currency_rate=self.currency_rate, date=self.date):
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
                    with Transaction().set_context(
                            currency_rate=line.currency_rate, date=self.date):
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
                    with Transaction().set_context(
                            currency_rate=line.currency_rate, date=self.date):
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
        with Transaction().set_context(
                currency_rate=self.currency_rate, date=self.date):
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
                    with Transaction().set_context(
                            currency_rate=line.currency_rate, date=self.date):
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
                with Transaction().set_context(
                        currency_rate=self.currency_rate, date=self.date):
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
        payment_lines_to_relate = defaultdict(list)

        for line in self.lines:
            origin = str(line.move_line.move_origin)
            origin = origin[:origin.find(',')]
            if origin not in ['account.invoice',
                    'account.voucher']:
                continue
            if line.amount == _ZERO:
                continue

            invoice = Invoice(line.move_line.move_origin.id)
            with Transaction().set_context(
                    currency_rate=self.currency_rate, date=self.date):
                amount = Currency.compute(self.currency,
                    line.amount, self.company.currency)

            reconcile_lines, remainder = \
                self.get_reconcile_lines_for_amount(invoice, amount,
                    lines_to_reconcile[line.account.id])

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
                    payment_lines_to_relate[invoice].append(move_line.id)

        if payment_lines_to_relate:
            for invoice, payment_lines in payment_lines_to_relate.items():
                Invoice.write([invoice], {
                    'payment_lines': [('add', list(set(payment_lines)))],
                    })

        if lines_to_reconcile:
            for lines_ids in lines_to_reconcile.values():
                if not lines_ids:
                    continue
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

    def get_reconcile_lines_for_amount(self, invoice, amount, reconcile_lines):
        '''
        Return list of lines and the remainder to make reconciliation.
        '''
        if self.voucher_type == 'payment':
            amount = -amount
        party = invoice.party
        Result = namedtuple('Result', ['lines', 'remainder'])

        lines = [
            l for l in invoice.payment_lines + invoice.lines_to_pay
            if not l.reconciliation
            and (not invoice.account.party_required or l.party == party)
            and (l.id not in reconcile_lines)]

        best = Result([], invoice.total_amount)
        for n in range(len(lines), 0, -1):
            for comb_lines in combinations(lines, n):
                remainder = sum((l.debit - l.credit) for l in comb_lines)
                remainder -= amount
                result = Result(list(comb_lines), remainder)
                if invoice.currency.is_zero(remainder):
                    return result
                if abs(remainder) < abs(best.remainder):
                    best = result
        return best

    def create_cancel_move(self):
        pool = Pool()
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Period = pool.get('account.period')
        Reconciliation = pool.get('account.move.reconciliation')
        Invoice = pool.get('account.invoice')
        PaymentLine = pool.get('account.invoice-account.move.line')

        reconciliations = [x.reconciliation for x in self.move.lines
                if x.reconciliation]
        with Transaction().set_user(0, set_context=True):
            if reconciliations:
                Reconciliation.delete(reconciliations)

        # Remove payment lines from their invoices.
        payments = defaultdict(list)
        ids = list(map(int, self.move.lines))
        for sub_ids in grouped_slice(ids):
            payment_lines = PaymentLine.search([
                ('line', 'in', list(sub_ids)),
                ])
            for payment_line in payment_lines:
                payments[payment_line.invoice].append(payment_line.line)
        to_write = []
        for invoice, lines in payments.items():
            to_write.append([invoice])
            to_write.append({'payment_lines': [('remove', lines)]})
        if to_write:
            Invoice.write(*to_write)

        cancelled_move, = Move.copy([self.move], {
            'period': Period.find(self.company.id, date=self.move.date),
            'date': self.move.date,
            })
        self.write([self], {
            'move_cancelled': cancelled_move.id,
            })

        for line in cancelled_move.lines:
            aux = line.debit
            line.debit = line.credit
            line.credit = aux
            line.amount_second_currency = (line.amount_second_currency * -1 if
                line.amount_second_currency else _ZERO)
            line.save()

        Move.post([self.move_cancelled])

        lines_to_reconcile = defaultdict(list)
        for line in self.move.lines:
            if line.account.reconcile:
                lines_to_reconcile[line.account.id].append(line)
        for cancel_line in cancelled_move.lines:
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
    @Workflow.transition('cancelled')
    def cancel(cls, vouchers):
        for voucher in vouchers:
            voucher.create_cancel_move()


class AccountVoucherLine(ModelSQL, ModelView):
    'Account Voucher Line'
    __name__ = 'account.voucher.line'

    _states = {'readonly': True}

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE')
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
        ], 'Type')
    move_line = fields.Many2One('account.move.line', 'Move Line')
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)
    date_expire = fields.Function(fields.Date('Expire date'),
        'get_expire_date')
    currency_rate = fields.Numeric('Currency rate', digits=(12, 6),
        states=_states)

    del _states

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        #cls._sql_indexes.update({
            #Index(t, (t.line_type, Index.Equality())),
            #})

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
        required=True, ondelete='CASCADE')
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
        ], 'Type', states=_states)
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states=_states)
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)
    currency_rate = fields.Numeric('Currency rate', digits=(12, 6),
        states=_states)

    del _states

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        #cls._sql_indexes.update({
            #Index(t, (t.line_type, Index.Equality())),
            #})


class AccountVoucherLineDebits(ModelSQL, ModelView):
    'Account Voucher Line Debits'
    __name__ = 'account.voucher.line.debits'

    _states = {'readonly': True}

    voucher = fields.Many2One('account.voucher', 'Voucher',
        required=True, ondelete='CASCADE')
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
        ], 'Type', states=_states)
    move_line = fields.Many2One('account.move.line', 'Move Line',
        states=_states)
    amount_original = fields.Numeric('Original Amount',
        digits=(16, 2), states=_states)
    amount_unreconciled = fields.Numeric('Unreconciled amount',
        digits=(16, 2), states=_states)
    date = fields.Date('Date', states=_states)
    currency_rate = fields.Numeric('Currency rate', digits=(12, 6),
        states=_states)

    del _states

    @classmethod
    def __setup__(cls):
        super().__setup__()
        t = cls.__table__()
        #cls._sql_indexes.update({
            #Index(t, (t.line_type, Index.Equality())),
            #})


class AccountVoucherLinePaymode(ModelSQL, ModelView):
    'Account Voucher Line Pay Mode'
    __name__ = 'account.voucher.line.paymode'

    voucher = fields.Many2One('account.voucher', 'Voucher')
    pay_mode = fields.Many2One('account.voucher.paymode', 'Pay Mode',
        required=True)
    pay_amount = fields.Numeric('Pay Amount', digits=(16, 2), required=True)

    @classmethod
    def __setup__(cls):
        super(AccountVoucherLinePaymode, cls).__setup__()
        cls._buttons.update({
                'calculate_remaining_amount': {
                    'invisible': ~Eval('_parent_voucher.state').in_(
                        ['draft', 'calculated']),
                    },
                })

    @staticmethod
    def default_pay_amount():
        return Decimal('0.0')

    @classmethod
    def calculate_remaining_amount(cls, paymodes):
        for p in paymodes:
            p.pay_amount = p.voucher.amount_invoices - p.voucher.amount
            p.save()


class AccountVoucherReport(Report):
    __name__ = 'account.voucher'

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
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
