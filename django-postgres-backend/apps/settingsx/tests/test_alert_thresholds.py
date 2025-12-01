from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from apps.settingsx.models import AlertThresholds


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
