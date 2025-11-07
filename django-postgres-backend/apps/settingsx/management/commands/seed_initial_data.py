from django.core.management.base import BaseCommand
from apps.settingsx.models import BusinessProfile, DocCounter, SettingKV
from apps.catalog.models import ProductCategory
from apps.inventory.models import RackRule


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
            ("PO", "PO-"),
            ("GRN", "GRN-"),
            ("TRANSFER", "TR-"),
            ("INVOICE", "INV-"),
        ]
        for doc, prefix in counters:
            DocCounter.objects.get_or_create(document_type=doc, defaults=dict(prefix=prefix, next_number=1, padding_int=5))

        defaults = {
            "ALERT_LOW_STOCK_DEFAULT": "50",
            "ALERT_EXPIRY_WARNING_DAYS": "60",
            "ALERT_EXPIRY_CRITICAL_DAYS": "30",
            "ALLOW_NEGATIVE_STOCK": "false",
        }
        for k, v in defaults.items():
            SettingKV.objects.get_or_create(key=k, defaults=dict(value=v))

        # Seed product categories
        for name in ["Tablets", "Syrups", "Injections"]:
            ProductCategory.objects.get_or_create(name=name)

        # Seed a couple of rack rules
        RackRule.objects.get_or_create(rack_code="A1", location_id=1, manufacturer_name="ACME", defaults={"is_active": True})
        RackRule.objects.get_or_create(rack_code="B1", location_id=1, manufacturer_name="Zen Labs", defaults={"is_active": True})

        self.stdout.write(self.style.SUCCESS("Seed data created/updated."))

