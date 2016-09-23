#This file is part of the account_voucher_ar module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from decimal import Decimal
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
        Date = Pool().get('ir.date')

        default = {
            'lines': [],
        }
        Invoice = Pool().get('account.invoice')

        invoice = Invoice(Transaction().context.get('active_id'))
        default['date'] = Date.today()
        default['party'] = invoice.party.id
        default['currency'] = invoice.currency.id
        default['pay_invoice'] = invoice.id

        amount_to_pay = Decimal('0.0')
        if invoice.type in ['in_invoice', 'in_credit_note']:
            default['voucher_type'] = 'payment'
            line_type = 'cr'
        if invoice.type in ['out_invoice', 'out_credit_note']:
            default['voucher_type'] = 'receipt'
            line_type = 'dr'
            amount_to_pay = invoice.amount_to_pay

        line_to_pay, = invoice.lines_to_pay

        lines = {
            'name': invoice.number,
            'account': invoice.account.id,
            'amount': amount_to_pay,
            'amount_original': invoice.total_amount,
            'amount_unreconciled': invoice.amount_to_pay,
            'line_type': line_type,
            'move_line': line_to_pay.id,
            'date': invoice.invoice_date,
            }
        default['lines'].append(lines)

        return default
