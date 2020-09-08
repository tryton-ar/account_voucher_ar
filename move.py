# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval, If, Bool


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        return super()._get_origin() + ['account.voucher']


class Line(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    amount_residual = fields.Function(fields.Numeric('Amount Residual',
        digits=(16, If(Bool(Eval('second_currency_digits')),
            Eval('second_currency_digits', 2),
            Eval('currency_digits', 2))),
        depends=['second_currency_digits', 'currency_digits']),
        'get_amount_residual')
    voucher_payments = fields.One2Many('account.voucher.line', 'move_line',
        'Voucher Payments', readonly=True)

    @classmethod
    def get_amount_residual(cls, lines, name):
        amounts = {}
        for line in lines:
            if line.reconciliation or not (
                    line.account.type.payable or line.account.type.receivable):
                amounts[line.id] = Decimal('0')
                continue
            amount = abs(line.credit - line.debit)

            for payment in line.voucher_payments:
                if payment.voucher and payment.voucher.state == 'posted':
                    amount -= payment.amount

            amounts[line.id] = amount
        return amounts
