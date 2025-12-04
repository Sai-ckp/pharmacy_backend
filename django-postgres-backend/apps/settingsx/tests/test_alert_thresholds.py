from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.settingsx.models import AlertThresholds, SettingKV


class AlertThresholdsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="settingstester", password="pass123", is_staff=True)
        self.client.force_authenticate(self.user)

    def test_get_and_update_thresholds(self):
        resp = self.client.get("/api/v1/settings/alert-thresholds/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("critical_expiry_days", resp.data)

        resp_put = self.client.put("/api/v1/settings/alert-thresholds/", {"critical_expiry_days": 20}, format="json")
        self.assertEqual(resp_put.status_code, status.HTTP_200_OK)
        thr = AlertThresholds.objects.first()
        self.assertEqual(thr.critical_expiry_days, 20)

    def test_settings_group_save_updates_alerts_model(self):
        payload = {
            "alerts": {
                "ALERT_EXPIRY_CRITICAL_DAYS": "15",
                "ALERT_EXPIRY_WARNING_DAYS": "35",
                "ALERT_LOW_STOCK_DEFAULT": "75",
            }
        }
        resp = self.client.post("/api/v1/settings/app/save", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        thr = AlertThresholds.objects.first()
        self.assertEqual(thr.critical_expiry_days, 15)
        self.assertEqual(thr.warning_expiry_days, 35)
        self.assertEqual(thr.low_stock_default, 75)
        # Ensure these keys are not duplicated in SettingKV store
        for key in payload["alerts"].keys():
            self.assertFalse(SettingKV.objects.filter(key=key).exists())
