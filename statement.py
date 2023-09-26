# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import fields, Workflow
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction


class AccountVoucherPayMode(metaclass=PoolMeta):
    __name__ = 'account.voucher.paymode'

    company = fields.Many2One('company.company', "Company",
        states={
            'required': Bool(Eval('statement_reconcile')),
            })
    statement_reconcile = fields.Boolean('Statement Conciliation')
    statement_journal = fields.Many2One(
        'account.statement.journal', "Journal",
        domain=[
            ('company', '=', Eval('company', -1)),
            ('account', '=', Eval('account', -1)),
            ],
        states={
            'invisible': ~Bool(Eval('statement_reconcile')),
            'required': Bool(Eval('statement_reconcile')),
            })

    @classmethod
    def default_company(cls):
        return Transaction().context.get('company')

    @staticmethod
    def default_statement_reconcile():
        return False


class AccountVoucherLinePaymode(metaclass=PoolMeta):
    __name__ = 'account.voucher.line.paymode'

    related_statement_line = fields.Many2One('account.statement.line',
        'Statement Line', readonly=True)


class Statement(metaclass=PoolMeta):
    __name__ = 'account.statement'

    @classmethod
    @Workflow.transition('validated')
    def validate_statement(cls, statements):
        pool = Pool()
        PayMode = pool.get('account.voucher.line.paymode')
        StatementLine = Pool().get('account.statement.line')

        super(Statement, cls).validate_statement(statements)
        # Remove created draft moves when line is related to paymodes
        lines = [l for s in statements for l in s.lines
            if isinstance(l.related_to, PayMode)]
        StatementLine.delete_move(lines)


class StatementLine(metaclass=PoolMeta):
    __name__ = 'account.statement.line'

    statement_journal = fields.Function(
        fields.Many2One('account.statement.journal', 'Statement Journal'),
        'on_change_with_statement_journal')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls.related_to.domain['account.voucher.line.paymode'] = ['OR',
            [('related_statement_line', '=', Eval('id', -1))],
            [('voucher.company', '=', Eval('company', -1)),
                If(Bool(Eval('voucher.party')),
                    ('voucher.party', '=', Eval('party')),
                    ()),
                ('pay_mode.statement_reconcile', '=', True),
                ('pay_mode.statement_journal', '=',
                    Eval('statement_journal', -1)),
                ('related_statement_line', '=', None),
                ('voucher.state', 'in', ['posted']),
                ('voucher.currency', '=', Eval('currency', -1)),
                ('voucher.voucher_type', '=',
                    If(Eval('amount', 0) > 0, 'receipt',
                        If(Eval('amount', 0) < 0, 'payment', ''))),
                ('pay_amount', '=', Eval('abs_amount', 0)),
            ]]
        cls.related_to.search_order['account.voucher.line.paymode'] = [
            ('pay_amount', 'ASC'),
            ]

    @fields.depends('statement')
    def on_change_with_statement_journal(self, name=None):
        if self.statement:
            return self.statement.journal.id
        return None

    @classmethod
    def _get_relations(cls):
        return super()._get_relations() + ['account.voucher.line.paymode']

    @property
    @fields.depends('related_to')
    def voucher_paymode(self):
        pool = Pool()
        VoucherPaymode = pool.get('account.voucher.line.paymode')
        related_to = getattr(self, 'related_to', None)
        if isinstance(related_to, VoucherPaymode) and related_to.id >= 0:
            return related_to

    @voucher_paymode.setter
    def voucher_paymode(self, value):
        self.related_to = value

    @fields.depends('party', 'statement', methods=['voucher_paymode'])
    def on_change_related_to(self):
        super().on_change_related_to()
        if self.voucher_paymode:
            if not self.party:
                self.party = self.voucher_paymode.voucher.party
            if self.voucher_paymode.pay_mode:
                self.account = self.voucher_paymode.pay_mode.account

    @classmethod
    def write(cls, *args):
        pool = Pool()
        PayMode = pool.get('account.voucher.line.paymode')

        actions = iter(args)
        to_update = {}
        for lines, values in zip(actions, actions):
            if 'related_to' in values:
                if values['related_to'] is None:
                    if isinstance(lines[0].related_to, PayMode):
                        to_update[lines[0].related_to.id] = None
                elif values['related_to'].split(',')[0] == PayMode.__name__:
                    paymode_id = int(values['related_to'].split(',')[1])
                    to_update[paymode_id] = lines[0].id
        super(StatementLine, cls).write(*args)
        cls.update_paymode_lines(to_update)

    def update_paymode_lines(to_update):
        pool = Pool()
        PayMode = pool.get('account.voucher.line.paymode')

        paymodes = []
        for key in to_update:
            paymode = PayMode(key)
            paymode.related_statement_line = to_update[key]
            paymodes.append(paymode)
        PayMode.save(paymodes)
