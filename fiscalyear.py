# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta

__all__ = ['FiscalYear', 'RenewFiscalYear']


class FiscalYear(metaclass=PoolMeta):
    __name__ = 'account.fiscalyear'

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


class RenewFiscalYear(metaclass=PoolMeta):
    __name__ = 'account.fiscalyear.renew'

    def fiscalyear_defaults(self):
        pool = Pool()
        Sequence = pool.get('ir.sequence')

        defaults = super(RenewFiscalYear, self).fiscalyear_defaults()

        prev_payment_sequence = Sequence(
            self.start.previous_fiscalyear.payment_sequence.id)
        payment_sequence, = Sequence.copy([prev_payment_sequence])
        if self.start.reset_sequences:
            payment_sequence.number_next = 1
        else:
            payment_sequence.number_next = prev_payment_sequence.number_next
        payment_sequence.save()
        defaults['payment_sequence'] = payment_sequence.id

        prev_receipt_sequence = Sequence(
            self.start.previous_fiscalyear.receipt_sequence.id)
        receipt_sequence, = Sequence.copy([prev_receipt_sequence])
        if self.start.reset_sequences:
            receipt_sequence.number_next = 1
        else:
            receipt_sequence.number_next = prev_receipt_sequence.number_next
        receipt_sequence.save()
        defaults['receipt_sequence'] = receipt_sequence.id

        return defaults
