================
Voucher Scenario
================

Imports::
    >>> import datetime as dt
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.currency.tests.tools import get_currency
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart
    >>> from trytond.modules.account_ar.tests.tools import get_accounts
    >>> from trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account_voucher_ar.tests.tools import \
    ...     set_fiscalyear_voucher_sequences
    >>> from trytond.modules.account_invoice_ar.tests.tools import \
    ...     get_tax
    >>> today = dt.date.today()

Install account_voucher_ar::

    >>> config = activate_modules('account_voucher_ar')

Create company::

    >>> currency = get_currency('ARS')
    >>> _ = create_company(currency=currency)
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'ar_vat'
    >>> tax_identifier.code = '30710158254' # gcoop CUIT
    >>> company.party.iva_condition = 'responsable_inscripto'
    >>> company.party.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_voucher_sequences(
    ...     set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company)))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]
    >>> period_ids = [p.id for p in fiscalyear.periods]

Create chart of accounts::

    >>> _ = create_chart(company, chart='account_ar.root_ar')
    >>> accounts = get_accounts(company)
    >>> account_receivable = accounts['receivable']
    >>> account_revenue = accounts['revenue']
    >>> account_expense = accounts['expense']
    >>> account_cash = accounts['cash']

Create taxes::

    >>> sale_tax = get_tax('IVA Ventas 21%')
    >>> sale_tax_nogravado = get_tax('IVA Ventas No Gravado')

Create payment method voucher_ar::

    >>> AccountVoucherPayMode = Model.get('account.voucher.paymode')
    >>> paymode = AccountVoucherPayMode()
    >>> paymode.name = 'Cash'
    >>> paymode.account = account_cash
    >>> paymode.save()


Create payment method::

    >>> Journal = Model.get('account.journal')
    >>> PaymentMethod = Model.get('account.invoice.payment.method')
    >>> Sequence = Model.get('ir.sequence')
    >>> journal_cash, = Journal.find([('type', '=', 'cash')])
    >>> payment_method = PaymentMethod()
    >>> payment_method.name = 'Cash'
    >>> payment_method.journal = journal_cash
    >>> payment_method.credit_account = account_cash
    >>> payment_method.debit_account = account_cash
    >>> payment_method.save()

Create Write Off method::

    >>> WriteOff = Model.get('account.move.reconcile.write_off')
    >>> sequence_journal, = Sequence.find(
    ...     [('sequence_type.name', '=', "Account Journal")], limit=1)
    >>> journal_writeoff = Journal(name='Write-Off', type='write-off',
    ...     sequence=sequence_journal)
    >>> journal_writeoff.save()
    >>> writeoff_method = WriteOff()
    >>> writeoff_method.name = 'Rate loss'
    >>> writeoff_method.journal = journal_writeoff
    >>> writeoff_method.credit_account = account_expense
    >>> writeoff_method.debit_account = account_expense
    >>> writeoff_method.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> party.iva_condition = 'consumidor_final'
    >>> party.account_receivable = account_receivable
    >>> party.save()

Create party2::

    >>> Party = Model.get('party.party')
    >>> party2 = Party(name='Party')
    >>> party2.account_receivable = account_receivable
    >>> party2.save()

Create account category::

    >>> ProductCategory = Model.get('product.category')
    >>> account_category = ProductCategory(name="Account Category")
    >>> account_category.accounting = True
    >>> account_category.account_expense = account_expense
    >>> account_category.account_revenue = account_revenue
    >>> account_category.customer_taxes.append(sale_tax)
    >>> account_category.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.account_category = account_category
    >>> template.save()
    >>> product, = template.products

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> payment_term = PaymentTerm(name='Term')
    >>> line = payment_term.lines.new(type='percent', ratio=Decimal('.5'))
    >>> delta, = line.relativedeltas
    >>> delta.days = 20
    >>> line = payment_term.lines.new(type='remainder')
    >>> delta = line.relativedeltas.new(days=40)
    >>> payment_term.save()

Create invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> InvoiceLine = Model.get('account.invoice.line')
    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.payment_term = None
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.account = account_revenue
    >>> line.taxes.append(sale_tax_nogravado)
    >>> line.description = 'Test'
    >>> line.quantity = 1
    >>> line.unit_price = Decimal(20)
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('262.00')
    >>> invoice.save()

Post invoice::

    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.code
    '30710158254'
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('42.00')
    >>> invoice.total_amount
    Decimal('262.00')

Pay invoice::

    >>> AccountVoucher = Model.get('account.voucher')
    >>> LinePaymode = Model.get('account.voucher.line.paymode')
    >>> voucher = AccountVoucher()
    >>> voucher.party = invoice.party
    >>> voucher.date = today
    >>> voucher.voucher_type = 'receipt'
    >>> voucher.journal = journal_cash
    >>> voucher.currency = invoice.currency
    >>> payment_line, = voucher.lines
    >>> payment_line.amount = payment_line.amount_unreconciled
    >>> pay_line = LinePaymode()
    >>> voucher.pay_lines.append(pay_line)
    >>> pay_line.pay_mode = paymode
    >>> pay_line.pay_amount = invoice.total_amount
    >>> voucher.save()
    >>> voucher.click('post')
    >>> voucher.state
    'posted'
    >>> bool(voucher.move)
    True
    >>> invoice.reload()
    >>> invoice.state
    'paid'
    >>> len(invoice.payment_lines)
    1

Cancel voucher::

    >>> voucher.click('cancel')
    >>> voucher.state
    'cancelled'
    >>> bool(voucher.move_cancelled)
    True
    >>> invoice.reload()
    >>> invoice.state
    'posted'
    >>> len(invoice.payment_lines)
    0

Advance payment::

    >>> AccountVoucher = Model.get('account.voucher')
    >>> LinePaymode = Model.get('account.voucher.line.paymode')
    >>> voucher = AccountVoucher()
    >>> voucher.party = party
    >>> voucher.date = today
    >>> voucher.voucher_type = 'receipt'
    >>> voucher.journal = journal_cash
    >>> voucher.currency = invoice.currency
    >>> del voucher.lines[:]
    >>> pay_line = LinePaymode()
    >>> voucher.pay_lines.append(pay_line)
    >>> pay_line.pay_mode = paymode
    >>> pay_line.pay_amount = Decimal('100')
    >>> voucher.save()
    >>> voucher.click('post')
    >>> voucher.state
    'posted'
    >>> bool(voucher.move)
    True

Pay invoice with advance payment::

    >>> AccountVoucher = Model.get('account.voucher')
    >>> LinePaymode = Model.get('account.voucher.line.paymode')
    >>> voucher = AccountVoucher()
    >>> voucher.party = party
    >>> voucher.date = today
    >>> voucher.voucher_type = 'receipt'
    >>> voucher.journal = journal_cash
    >>> voucher.currency = invoice.currency
    >>> payment_line, = voucher.lines
    >>> payment_line.amount = payment_line.amount_unreconciled
    >>> pay_line = LinePaymode()
    >>> voucher.pay_lines.append(pay_line)
    >>> pay_line.pay_mode = paymode
    >>> pay_line.pay_amount = Decimal('162')
    >>> voucher.save()
    >>> voucher.click('post')
    >>> voucher.state
    'posted'
    >>> bool(voucher.move)
    True
    >>> invoice.reload()
    >>> invoice.state
    'paid'

Duplicate invoice with payment_term::

    >>> invoice, = invoice.duplicate()
    >>> invoice.state
    'draft'
    >>> invoice.payment_term = payment_term
    >>> invoice.party = party2
    >>> invoice.click('post')

Partial payment::

    >>> AccountVoucher = Model.get('account.voucher')
    >>> LinePaymode = Model.get('account.voucher.line.paymode')
    >>> voucher = AccountVoucher()
    >>> voucher.party = party2
    >>> voucher.date = today
    >>> voucher.voucher_type = 'receipt'
    >>> voucher.journal = journal_cash
    >>> voucher.currency = invoice.currency
    >>> payment_line, = voucher.lines
    >>> payment_line.amount = payment_line.amount_unreconciled
    >>> pay_line = LinePaymode()
    >>> voucher.pay_lines.append(pay_line)
    >>> pay_line.pay_mode = paymode
    >>> pay_line.pay_amount = invoice.total_amount
    >>> voucher.save()
    >>> voucher.click('post')
    >>> voucher.state
    'posted'
    >>> invoice.reload()
    >>> invoice.state
    'paid'
