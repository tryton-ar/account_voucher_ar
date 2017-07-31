# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool

__all__ = ['PayInvoice']


class PayInvoice(Wizard):
    'Pay Invoice'
    __name__ = 'account.invoice.pay'

    start = StateView('account.voucher',
        'account_voucher_ar.account_voucher_form', [
            Button('Close', 'end', 'tryton-ok', default=True),
            ])

    def default_start(self, fields):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')

        default = {
            'lines': [],
            }

        invoice = Invoice(Transaction().context.get('active_id'))
        default['date'] = Date.today()
        default['party'] = invoice.party.id
        default['currency'] = invoice.currency.id
        default['pay_invoice'] = invoice.id

        if invoice.type in ['in_invoice', 'in_credit_note']:
            default['voucher_type'] = 'payment'
            line_type = 'cr'
        if invoice.type in ['out_invoice', 'out_credit_note']:
            default['voucher_type'] = 'receipt'
            line_type = 'dr'

        for line in invoice.lines_to_pay:
            if line_type == 'cr':
                amount = line.credit
            else:
                amount = line.debit
            amount_residual = abs(line.amount_residual)

            lines = {
                'name': invoice.number,
                'account': invoice.account.id,
                'amount': abs(line.amount),
                'amount_original': amount,
                'amount_unreconciled': amount_residual,
                'line_type': line_type,
                'move_line': line.id,
                'date': invoice.invoice_date,
                }
            default['lines'].append(lines)

        return default
