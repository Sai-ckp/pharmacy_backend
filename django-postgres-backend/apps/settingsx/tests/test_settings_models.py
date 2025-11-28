from decimal import Decimal

from django.test import TestCase

from apps.settingsx.models import NotificationSettings, TaxBillingSettings
from apps.settingsx.serializers import NotificationSettingsSerializer, TaxBillingSettingsSerializer


class SettingsModelsTests(TestCase):
    def test_notification_settings_save(self):
        obj = NotificationSettings.objects.create(enable_email=True, notification_email="alerts@example.com")
        ser = NotificationSettingsSerializer(obj)
        self.assertTrue(ser.data["enable_email"])
        self.assertEqual(ser.data["notification_email"], "alerts@example.com")

    def test_tax_billing_validation(self):
        obj = TaxBillingSettings.objects.create(gst_rate=Decimal("5.00"), calc_method="INCLUSIVE")
        ser = TaxBillingSettingsSerializer(obj, data={"gst_rate": "12.00"}, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
        ser.save()
        self.assertEqual(str(TaxBillingSettings.objects.get(id=obj.id).gst_rate), "12.00")
