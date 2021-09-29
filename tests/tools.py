# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
from proteus import Model

__all__ = ['set_fiscalyear_voucher_sequences']


def set_fiscalyear_voucher_sequences(fiscalyear, config=None):
    "Set voucher sequences to fiscalyear"
    SequenceType = Model.get('ir.sequence.type', config=config)
    Sequence = Model.get('ir.sequence', config=config)

    payment_seq_type, = SequenceType.find([
        ('name', '=', 'Account Voucher Payment'),
        ], limit=1)
    payment_seq = Sequence(
        name=fiscalyear.name,
        sequence_type=payment_seq_type,
        company=fiscalyear.company)
    payment_seq.save()
    fiscalyear.payment_sequence = payment_seq

    receipt_seq_type, = SequenceType.find([
        ('name', '=', 'Account Voucher Receipt'),
        ], limit=1)
    receipt_seq = Sequence(
        name=fiscalyear.name,
        sequence_type=receipt_seq_type,
        company=fiscalyear.company)
    receipt_seq.save()
    fiscalyear.receipt_sequence = receipt_seq

    return fiscalyear
