#This file is part of the account_voucher_ar module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.


from trytond.pool import Pool
from .move import *
from .account_voucher_ar import *


def register():
    Pool.register(
        Move,
        Line,
        AccountVoucherSequence,
        AccountVoucherPayMode,
        AccountVoucher,
        AccountVoucherLine,
        AccountVoucherLineCredits,
        AccountVoucherLineDebits,
        AccountVoucherLinePaymode,
        module='account_voucher_ar', type_='model')

