# This file is part of the account_voucher_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.wizard import StateView, Button
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.i18n import gettext


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._buttons['pay']['invisible'] = (Eval('state') != 'posted')


class VoucherStateView(StateView):
    def get_view(self, wizard, state_name):
        with Transaction().set_context(invoice_pay=True):
            return super(VoucherStateView, self).get_view(
                wizard, state_name)


class PayInvoice(metaclass=PoolMeta):
    __name__ = 'account.invoice.pay'

    @classmethod
    def __setup__(cls):
        super(PayInvoice, cls).__setup__()
        cls.start = VoucherStateView('account.voucher',
            'account_voucher_ar.account_voucher_form', [
                Button('Close', 'end', 'tryton-ok', default=True),
                ])

    def default_start(self, fields):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')

        default = {}

        invoice = Invoice(Transaction().context.get('active_id'))
        default['date'] = Date.today()
        default['party'] = invoice.party.id
        default['currency'] = invoice.currency.id
        default['pay_invoice'] = invoice.id
        if invoice.type == 'in':
            default['voucher_type'] = 'payment'
        elif invoice.type == 'out':
            default['voucher_type'] = 'receipt'
        return default


class CreditInvoice(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit'

    @classmethod
    def _amount_difference(cls, invoice):
        return invoice.amount_to_pay != invoice.total_amount

    def default_start(self, fields):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        default = super().default_start(fields)
        default.update({
            'with_refund': True,
            'with_refund_allowed': True,
            })
        for invoice in Invoice.browse(Transaction().context['active_ids']):
            if (invoice.state != 'posted' or invoice.type == 'in' or
                    self._amount_difference(invoice)):
                default['with_refund'] = False
                default['with_refund_allowed'] = False
                break
            if invoice.payment_lines:
                default['with_refund'] = False
        return default

    def do_credit(self, action):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        if self.start.with_refund:
            invoices = Invoice.browse(Transaction().context['active_ids'])
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
        return super().do_credit(action)
