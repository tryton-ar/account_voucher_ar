#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.wizard import Wizard
from trytond.pool import Pool


class InvoiceToPay(ModelView):
    _name = 'account.voucher.invoice_to_pay'

    name = fields.Char('Name')
    party = fields.Many2One('party.party', 'Party')
    line_ids = fields.Many2Many('account.move.line', None, None,
        'Account Moves')

InvoiceToPay()


class SelectInvoices(Wizard):
    'Open Chart Of Account'
    _name = 'account.voucher.select_invoices'

    def search_lines(self, data):
        res = {}
        voucher_obj = Pool().get('account.voucher')
        voucher = voucher_obj.browse(data['id'])
        move_line = Pool().get('account.move.line')

        if voucher.voucher_type == 'receipt':
            account_types = ['receivable']
        else:
            account_types = ['payable']

        line_domain = [
            ('party', '=', voucher.party.id),
            ('account.kind', 'in', account_types),
            ('state', '=', 'valid'),
            ('reconciliation', '=', False),
        ]

        move_ids = move_line.search(line_domain)
        res['line_ids'] = move_ids
        return res

    states = {
        'init': {
            'actions': ['search_lines'],
            'result': {
                'type': 'form',
                'object': 'account.voucher.invoice_to_pay',
                'state': [
                    ('end', 'Cancel', 'tryton-cancel'),
                    ('open', 'Open', 'tryton-ok', True),
                ],
            },
        },
        'open': {
            'result': {
                'type': 'action',
                'action': '_action_add_lines',
                'state': 'end',
            },
        },
    }

    def _action_add_lines(self, data):
        res = {}
        total_credit = 0
        total_debit = 0
        voucher_line_obj = Pool().get('account.voucher.line')
        voucher = Pool().get('account.voucher').browse(data['id'])
        move_line_obj = Pool().get('account.move.line')
        move_ids = data['form']['line_ids'][0][1]

        for line in move_line_obj.browse(move_ids):
            total_credit += line.credit
            total_debit += line.debit
            if line.credit:
                line_type = 'cr'
                amount = line.credit
            else:
                amount = line.debit
                line_type = 'dr'

            voucher_line_obj.create({
                'voucher_id': data['id'],
                'name': line.name,
                'account_id': line.account.id,
                'amount_original': amount,
                'amount_unreconciled': amount,
                'line_type': line_type,
                'move_line_id': line.id,
            })
        voucher.write(data['id'], {})

        return res

#    voucher_id = fields.Many2One('account.voucher', 'Voucher')
#    name = fields.Char('Name')
#    account_id = fields.Many2One('account.account', 'Account')
#    amount = fields.Float('Amount')
#    line_type = fields.Selection([
#        ('cr', 'Credit'),
#        ('dr', 'Debit'),
#        ], 'Type', select=True)
#    move_line_id = fields.Many2One('account.move.line', 'Move Line')
#    amount_original = fields.Float('Original Amount')
#    amount_unreconciled = fields.Float('Unreconciled amount')

SelectInvoices()
