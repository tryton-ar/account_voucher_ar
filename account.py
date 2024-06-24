# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.modules.company.model import CompanyValueMixin


class Configuration(metaclass=PoolMeta):
    __name__ = 'account.configuration'

    default_payment_journal = fields.MultiValue(fields.Many2One(
        'account.journal', 'Default Payment Journal'))
    default_payment_currency = fields.MultiValue(fields.Many2One(
        'currency.currency', 'Default Payment Currency'))
    default_receipt_journal = fields.MultiValue(fields.Many2One(
        'account.journal', 'Default Receipt Journal'))
    default_receipt_currency = fields.MultiValue(fields.Many2One(
        'currency.currency', 'Default Receipt Currency'))

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {'default_payment_journal', 'default_payment_currency',
                'default_receipt_journal', 'default_receipt_currency'}:
            return pool.get('account.configuration.default_voucher')
        return super().multivalue_model(field)


class ConfigurationDefaultVoucher(ModelSQL, CompanyValueMixin):
    'Account Configuration Default Voucher'
    __name__ = 'account.configuration.default_voucher'

    default_payment_journal = fields.Many2One(
        'account.journal', 'Default Payment Journal')
    default_payment_currency = fields.Many2One(
        'currency.currency', 'Default Payment Currency')
    default_receipt_journal = fields.Many2One(
        'account.journal', 'Default Receipt Journal')
    default_receipt_currency = fields.Many2One(
        'currency.currency', 'Default Receipt Currency')
