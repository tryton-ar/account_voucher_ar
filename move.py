# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        return super()._get_origin() + ['account.voucher']


class Line(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    amount_residual = fields.Function(fields.Numeric('Amount Residual',
        digits=(16, 2)), 'get_amount_residual')
    amount_residual_second_currency = fields.Function(fields.Numeric(
        'Amount Residual Second Currency', digits=(16, 2)),
        'get_amount_residual_second_currency')
    voucher_payments = fields.One2Many('account.voucher.line', 'move_line',
        'Voucher Payments', readonly=True)

    @classmethod
    def get_amount_residual(cls, lines, name):
        pool = Pool()
        Currency = pool.get('currency.currency')

        amounts = {}
        for line in lines:
            if line.reconciliation or not (
                    line.account.type.payable or line.account.type.receivable):
                amounts[line.id] = Decimal(0)
                continue
            amount = abs(line.credit - line.debit)

            for payment in line.voucher_payments:
                voucher = payment.voucher
                if voucher and voucher.state == 'posted':
                    if voucher.currency != voucher.company.currency:
                        with Transaction().set_context(
                                currency_rate=voucher.currency_rate,
                                date=voucher.date):
                            amount -= Currency.compute(voucher.currency,
                                payment.amount, voucher.company.currency)
                    else:
                        amount -= payment.amount
            amounts[line.id] = amount
        return amounts

    @classmethod
    def get_amount_residual_second_currency(cls, lines, name):
        pool = Pool()
        Currency = pool.get('currency.currency')

        amounts = {}
        for line in lines:
            if not line.amount_second_currency or line.reconciliation or not (
                    line.account.type.payable or line.account.type.receivable):
                amounts[line.id] = Decimal(0)
                continue
            amount = abs(line.amount_second_currency)

            for payment in line.voucher_payments:
                voucher = payment.voucher
                if voucher and voucher.state == 'posted':
                    if voucher.currency != voucher.company.currency:
                        amount -= payment.amount
                    else:
                        with Transaction().set_context(
                                currency_rate=voucher.currency_rate,
                                date=voucher.date):
                            amount -= Currency.compute(voucher.currency,
                                payment.amount, voucher.company.currency)
            amounts[line.id] = amount
        return amounts

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('voucher_payments', [])
        return super().copy(lines, default=default)
