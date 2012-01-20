#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name': 'Account Voucher',
    'version': '0.1',
    'author': 'Ignacio E. Parszyk',
    'email': 'iparszyk@thymbra.com',
    'website': 'http://thymbra.com',
    'depends': [
        'account',
        'account_invoice',
    ],
    'translation': ['es_CO.csv'],
    'description': '''
    Account Voucher
''',

    'xml': [
        'account_voucher_view.xml',
        'wizard/select_invoices.xml',
        'workflow.xml'
    ],
    'active': False,
}
