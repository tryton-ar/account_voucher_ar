# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal

from trytond.model import fields
from trytond.pool import Pool, PoolMeta

__all__ = ['Move', 'Line']


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def _get_origin(cls):
        return super(Move, cls)._get_origin() + ['account.voucher']


class Line(metaclass=PoolMeta):
    __name__ = 'account.move.line'

    amount_residual = fields.Function(fields.Numeric('Amount Residual',
        digits=(16, 2)), 'get_amount_residual')

    def get_amount_residual(self, name):
        Invoice = Pool().get('account.invoice')

        res = Decimal('0.0')
        if self.reconciliation or \
                not self.account.kind in ('payable', 'receivable'):
            return res

        move_line_total = self.debit - self.credit

        invoices = Invoice.search([
            ('move', '=', self.move.id),
        ])
        if invoices:
            invoice = invoices[0]
            for payment_line in invoice.payment_lines:
                if payment_line.id == self.id:
                    continue
                move_line_total += payment_line.debit - payment_line.credit
            res = move_line_total
        return res
