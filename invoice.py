# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta

__all__ = ['PayInvoice', 'CreditInvoice']


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

        if invoice.type == 'in':
            default['voucher_type'] = 'payment'
            line_type = 'cr'
            name = invoice.reference
        elif invoice.type == 'out':
            default['voucher_type'] = 'receipt'
            line_type = 'dr'
            name = invoice.number

        for line in invoice.lines_to_pay:
            if line_type == 'cr':
                amount = line.credit
            else:
                amount = line.debit
            amount_residual = abs(line.amount_residual)

            lines = {
                'name': name,
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


class CreditInvoice:
    __name__ = 'account.invoice.credit'
    __metaclass__ = PoolMeta

    @classmethod
    def __setup__(cls):
        super(CreditInvoice, cls).__setup__()
        cls._error_messages.update({
                'refund_with_amount_difference': ('You can not credit with refund '
                    'invoice "%s" because total amount is different than '
                    'amount to pay.'),
                })

    @classmethod
    def _amount_difference(cls, invoice):
        return invoice.amount_to_pay != invoice.total_amount

    def default_start(self, fields):
        Invoice = Pool().get('account.invoice')
        default = {
            'with_refund': True,
            'with_refund_allowed': True,
            }
        for invoice in Invoice.browse(Transaction().context['active_ids']):
            if (invoice.state != 'posted'
                    or self._amount_difference(invoice)
                    or invoice.type == 'in'):
                default['with_refund'] = False
                default['with_refund_allowed'] = False
                break
        return default

    def do_credit(self, action):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        refund = self.start.with_refund
        invoices = Invoice.browse(Transaction().context['active_ids'])

        if refund:
            for invoice in invoices:
                if invoice.state != 'posted':
                    self.raise_user_error('refund_non_posted',
                        (invoice.rec_name,))
                if self._amount_difference(invoice):
                    self.raise_user_error('refund_with_amount_difference',
                        (invoice.rec_name,))
                if invoice.type == 'in':
                    self.raise_user_error('refund_supplier', invoice.rec_name)

        credit_invoices = Invoice.credit(invoices, refund=refund)

        data = {'res_id': [i.id for i in credit_invoices]}
        if len(credit_invoices) == 1:
            action['views'].reverse()
        return action, data
