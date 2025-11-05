from django.core.management.base import BaseCommand
from apps.settingsx.models import BusinessProfile, DocCounter, Settings


class Command(BaseCommand):
    help = "Seed initial business profile, counters, and settings"

    def handle(self, *args, **options):
        BusinessProfile.objects.get_or_create(id=1, defaults=dict(
            business_name="Acme Pharmacy",
            email="info@example.com",
            phone="0000000000",
            address="Main Street",
            owner_name="Owner",
        ))

        counters = [
            ("INVOICE", "INV"),
            ("PO", "PO"),
            ("GRN", "GRN"),
        ]
        for doc, prefix in counters:
            DocCounter.objects.get_or_create(document_type=doc, defaults=dict(prefix=prefix, next_number=1001, padding_int=4))

        defaults = {
            "expiry_critical_days": "30",
            "expiry_warning_days": "60",
            "low_stock_threshold_default": "50",
            "pending_bill_alert_days": "7",
            "gst_rate_default": "12",
            "tax_calc_method": "INCLUSIVE",
        }
        for k, v in defaults.items():
            Settings.objects.get_or_create(key=k, defaults=dict(value=v))

        self.stdout.write(self.style.SUCCESS("Seed data created/updated."))

