from django.core.management.base import BaseCommand
from apps.governance.services import run_expiry_scan


class Command(BaseCommand):
    help = "Run expiry scan and emit event"

    def handle(self, *args, **options):
        result = run_expiry_scan()
        self.stdout.write(self.style.SUCCESS(f"Expiry scan done: {result}"))

