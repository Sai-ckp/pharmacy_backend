from django.core.management import call_command
from django.test import TestCase


class CommandSmokeTests(TestCase):
    def test_expiry_scan(self):
        call_command('expiry_scan')

    def test_low_stock_scan(self):
        call_command('low_stock_scan')

