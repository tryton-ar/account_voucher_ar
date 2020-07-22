# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.exceptions import UserError
from trytond.i18n import gettext

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
        Currency = pool.get('currency.currency')
        Date = pool.get('ir.date')

        default = {
            'lines': [],
            }

        invoice = Invoice(Transaction().context.get('active_id'))
        default['date'] = Date.today()
        default['party'] = invoice.party.id
        default['currency'] = invoice.currency.id
        default['pay_invoice'] = invoice.id

        second_currency = None
        if invoice.currency != invoice.company.currency:
            second_currency = invoice.currency

        if invoice.type == 'in':
            default['voucher_type'] = 'payment'
            line_type = 'cr'
            name = invoice.reference
        elif invoice.type == 'out':
            default['voucher_type'] = 'receipt'
            line_type = 'dr'
            name = invoice.number

        for line in sorted(invoice.lines_to_pay,
                key=lambda x: x.maturity_date):
            if line.reconciliation:
                continue

            if line_type == 'cr':
                amount = line.credit
            else:
                amount = line.debit

            amount_residual = abs(line.amount_residual)
            if second_currency:
                with Transaction().set_context(date=default['date']):
                    amount = Currency.compute(invoice.company.currency,
                        amount, invoice.currency)
                    amount_residual = Currency.compute(
                        invoice.company.currency, amount_residual,
                        invoice.currency)
            lines = {
                'name': name,
                'account': invoice.account.id,
                'amount': amount_residual,
                'amount_original': amount,
                'amount_unreconciled': amount_residual,
                'line_type': line_type,
                'move_line': line.id,
                'date': invoice.invoice_date,
                'date_expire': line.maturity_date,
                }
            default['lines'].append(lines)

        return default


class CreditInvoice(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit'

    @classmethod
    def _amount_difference(cls, invoice):
        return invoice.amount_to_pay != invoice.total_amount

    def default_start(self, fields):
        Invoice = Pool().get('account.invoice')

        default = super(CreditInvoice, self).default_start(fields)
        default.update({
            'with_refund': True,
            'with_refund_allowed': True,
            })
        for invoice in Invoice.browse(Transaction().context['active_ids']):
            if (invoice.state != 'posted' or
                    self._amount_difference(invoice) or invoice.type == 'in'):
                default['with_refund'] = False
                default['with_refund_allowed'] = False
                break
        return default

    def do_credit(self, action):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        try:
            action, data = super(CreditInvoice, self).do_credit(action)
        except UserError as e:
            refund = self.start.with_refund
            invoices = Invoice.browse(Transaction().context['active_ids'])

            if refund:
                for invoice in invoices:
                    if invoice.state != 'posted':
                        raise UserError(gettext(
                            'account_voucher_ar.msg_refund_non_posted',
                            invoice=invoice.rec_name))
                    if invoice.payment_lines:
                        raise UserError(gettext(
                            'account_voucher_ar.msg_refund_with_payement',
                            invoice=invoice.rec_name))
                    if invoice.type == 'in':
                        raise UserError(gettext(
                            'account_voucher_ar.msg_refund_supplier',
                            invoice=invoice.rec_name))

            credit_invoices = Invoice.credit(invoices, refund=refund)

            data = {'res_id': [i.id for i in credit_invoices]}
            if len(credit_invoices) == 1:
                action['views'].reverse()
        return action, data
