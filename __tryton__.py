#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name': 'Account Voucher Argentina',
    'version': '2.0.1',
    'author': 'Thymbra - Torre de Hanoi',
    'email': 'iparszyk@thymbra.com',
    'website': 'http://www.thymbra.com/',
    'description': '''Account Voucher for Argentina''',
    'depends': [
        'account',
        'account_invoice',
    ],
    'xml': [
        'account_voucher_ar.xml',
        'wizard/select_invoices.xml',
        'workflow.xml'
    ],
    'translation': [
        'es_CO.csv',
    ],
}
