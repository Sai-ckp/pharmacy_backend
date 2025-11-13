from django.core.management.base import BaseCommand
from apps.settingsx.models import BusinessProfile, DocCounter, SettingKV, PaymentMethod, PaymentTerm
from apps.catalog.models import ProductCategory, MedicineForm, Uom
from apps.inventory.models import RackRule, RackLocation


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
            # Alerts
            "ALERT_LOW_STOCK_DEFAULT": "50",
            "ALERT_EXPIRY_WARNING_DAYS": "60",
            "ALERT_EXPIRY_CRITICAL_DAYS": "30",
            # Inventory/stock behavior
            "ALLOW_NEGATIVE_STOCK": "false",
            # Tax & Billing
            "TAX_GST_RATE": "12",
            "TAX_CGST_RATE": "6",
            "TAX_SGST_RATE": "6",
            "TAX_CALC_METHOD": "INCLUSIVE",  # INCLUSIVE | EXCLUSIVE
            "INVOICE_PREFIX": "INV-",
            "INVOICE_START": "1001",
            "INVOICE_TEMPLATE": "STANDARD",
            "INVOICE_FOOTER": "Thank you for choosing our pharmacy",
            # Notifications
            "NOTIFY_EMAIL_ENABLED": "false",
            "NOTIFY_LOW_STOCK": "true",
            "NOTIFY_EXPIRY": "true",
            "NOTIFY_DAILY_REPORT": "false",
            "NOTIFY_EMAIL": "",
            "NOTIFY_SMS_ENABLED": "false",
            "NOTIFY_SMS_PHONE": "",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
        }
        for k, v in defaults.items():
            SettingKV.objects.get_or_create(key=k, defaults=dict(value=v))

        # Seed product categories
        for name in ["Tablets", "Syrups", "Injections"]:
            ProductCategory.objects.get_or_create(name=name)

        # Seed a couple of rack rules
        RackRule.objects.get_or_create(rack_code="A1", location_id=1, manufacturer_name="ACME", defaults={"is_active": True})
        RackRule.objects.get_or_create(rack_code="B1", location_id=1, manufacturer_name="Zen Labs", defaults={"is_active": True})

        # Seed Medicine Forms
        for name in ["Tablet", "Capsule", "Syrup", "Injection", "Ointment", "Drops"]:
            MedicineForm.objects.get_or_create(name=name)

        # Seed UOMs
        uoms = [
            ("Strip", "PACK"), ("Bottle", "PACK"), ("Box", "PACK"), ("Vial", "PACK"), ("Tube", "PACK"),
            ("Tablet", "BASE"), ("mL", "BASE"), ("g", "BASE"),
        ]
        for name, typ in uoms:
            Uom.objects.get_or_create(name=name, defaults={"uom_type": typ})

        # Seed Payment Methods
        for name in ["Cash", "Card", "UPI", "Credit", "Insurance"]:
            PaymentMethod.objects.get_or_create(name=name)

        # Seed Payment Terms
        terms = [("Immediate", 0), ("Net 15", 15), ("Net 30", 30), ("Net 45", 45), ("Net 60", 60)]
        for name, days in terms:
            PaymentTerm.objects.get_or_create(name=name, defaults={"days": days})

        # Seed Rack Locations
        for name in ["A1", "A2", "B1", "B2", "C1"]:
            RackLocation.objects.get_or_create(name=name)

        self.stdout.write(self.style.SUCCESS("Seed data created/updated."))

