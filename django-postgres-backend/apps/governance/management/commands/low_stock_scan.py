from django.core.management.base import BaseCommand
from apps.governance.services import run_low_stock_scan


class Command(BaseCommand):
    help = "Run low stock scan and emit event"

    def handle(self, *args, **options):
        result = run_low_stock_scan()
        self.stdout.write(self.style.SUCCESS(f"Low stock scan done: {len(result)} items"))

