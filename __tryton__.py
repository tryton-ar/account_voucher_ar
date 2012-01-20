#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name': 'Account Voucher',
    'version': '0.1',
    'author': 'Ignacio E. Parszyk',
    'email': 'iparszyk@thymbra.com',
    'website': 'http://thymbra.com',
    'description': '''Account Voucher''',
    'depends': [
        'account',
        'account_invoice',
    ],
    'xml': [
        'account_voucher_view.xml',
        'wizard/select_invoices.xml',
        'workflow.xml'
    ],
    'translation': [
        'es_CO.csv',
    ],
    'active': False,
}
