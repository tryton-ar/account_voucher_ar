# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
from proteus import Model

__all__ = ['set_fiscalyear_voucher_sequences']


def set_fiscalyear_voucher_sequences(fiscalyear, config=None):
    "Set voucher sequences to fiscalyear"
    Sequence = Model.get('ir.sequence', config=config)
    payment_seq = Sequence(name=fiscalyear.name,
        code='account.voucher.payment', company=fiscalyear.company)
    receipt_seq = Sequence(name=fiscalyear.name,
        code='account.voucher.receipt', company=fiscalyear.company)
    payment_seq.save()
    receipt_seq.save()
    fiscalyear.payment_sequence = payment_seq
    fiscalyear.receipt_sequence = receipt_seq
    return fiscalyear
