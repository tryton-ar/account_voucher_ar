# The COPYRIGHT file at the top level of this repository contains the
# full copyright notices and license terms.
import unittest
import doctest
import datetime
from decimal import Decimal
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import doctest_teardown
from trytond.tests.test_tryton import doctest_checker
from trytond.pool import Pool


class VoucherTestCase(ModuleTestCase):
    'VoucherTestCase module'
    module = 'account_voucher_ar'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            VoucherTestCase))
    suite.addTests(doctest.DocFileSuite('scenario_voucher.rst',
            tearDown=doctest_teardown, encoding='utf-8',
            checker=doctest_checker,
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite
