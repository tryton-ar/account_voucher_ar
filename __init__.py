# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import Pool
from . import move
from . import account
from . import fiscalyear
from . import account_voucher_ar
from . import invoice
from . import statement


def register():
    Pool.register(
        move.Move,
        move.Line,
        account.Configuration,
        account.ConfigurationDefaultVoucher,
        fiscalyear.FiscalYear,
        account_voucher_ar.AccountVoucherPayMode,
        account_voucher_ar.AccountVoucher,
        account_voucher_ar.AccountVoucherLine,
        account_voucher_ar.AccountVoucherLineCredits,
        account_voucher_ar.AccountVoucherLineDebits,
        account_voucher_ar.AccountVoucherLinePaymode,
        module='account_voucher_ar', type_='model')
    Pool.register(
        statement.AccountVoucherPayMode,
        statement.AccountVoucherLinePaymode,
        statement.Statement,
        statement.StatementLine,
        module='account_voucher_ar', type_='model',
        depends=['account_statement'])
    Pool.register(
        fiscalyear.RenewFiscalYear,
        invoice.PayInvoice,
        invoice.CreditInvoice,
        module='account_voucher_ar', type_='wizard')
    Pool.register(
        account_voucher_ar.AccountVoucherReport,
        module='account_voucher_ar', type_='report')
