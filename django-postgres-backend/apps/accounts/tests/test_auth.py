from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from core.models import SystemLicense
from apps.accounts.models import UserDevice


class AuthFlowTests(APITestCase):
    def setUp(self):
        self.password = "demoPass123"
        self.user = User.objects.create_user(
            username="demo", email="demo@example.com", password=self.password
        )
        today = date.today()
        self.license = SystemLicense.objects.create(
            license_key="TEST-LICENSE-KEY",
            status=SystemLicense.Status.ACTIVE,
            valid_from=today - timedelta(days=1),
            valid_to=today + timedelta(days=30),
        )

    def _login(self, password=None, device_id="device-001"):
        payload = {
            "username": self.user.username,
            "password": password or self.password,
            "device_id": device_id,
        }
        return self.client.post("/api/auth/login/", payload, format="json")

    def test_login_returns_tokens_and_license_info(self):
        resp = self._login()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["id"], self.user.id)
        self.assertIn("days_left", resp.data["license"])
        self.assertEqual(resp.data["license"]["valid_to"], self.license.valid_to.isoformat())

    def test_login_blocks_when_license_inactive(self):
        self.license.status = SystemLicense.Status.EXPIRED
        self.license.save()
        resp = self._login()
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            resp.data["detail"],
            "Your license has expired or is inactive. Please contact support@ckpsoftware.com to renew your license.",
        )

    def test_device_binding_and_mismatch(self):
        first = self._login(device_id="device-abc")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(UserDevice.objects.filter(user=self.user, device_id="device-abc").exists())

        mismatch = self._login(device_id="device-other")
        self.assertEqual(mismatch.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            mismatch.data["detail"],
            "This account is already registered on another device. To change your device, please contact support@ckpsoftware.com.",
        )

        allowed = self._login(device_id="device-abc")
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_full_password_reset_flow(self):
        with patch("apps.accounts.views.random.randint", return_value=123456):
            forgot = self.client.post(
                "/api/v1/accounts/forgot-password/",
                {"email": self.user.email},
                format="json",
            )
        self.assertEqual(forgot.status_code, status.HTTP_200_OK)
        verify = self.client.post(
            "/api/v1/accounts/verify-otp/",
            {"email": self.user.email, "otp": "123456"},
            format="json",
        )
        self.assertEqual(verify.status_code, status.HTTP_200_OK)
        uid = verify.data.get("uid")
        token = verify.data.get("token")
        self.assertTrue(uid)
        self.assertIn("token", verify.data)

        reset = self.client.post(
            "/api/v1/accounts/reset-password/",
            {"uid": uid, "token": token, "new_password": "Newpass123"},
            format="json",
        )
        self.assertEqual(reset.status_code, status.HTTP_200_OK)

        login = self._login(password="Newpass123")
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_logout_blacklists_refresh(self):
        login = self._login()
        refresh = login.data["refresh"]
        access = login.data["access"]

        auth_client = APIClient()
        auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout = auth_client.post("/api/v1/accounts/logout/", {"refresh": refresh}, format="json")
        self.assertEqual(logout.status_code, status.HTTP_200_OK)

        refresh_resp = self.client.post("/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_forgot_password_rejects_unknown_email(self):
        resp = self.client.post(
            "/api/v1/accounts/forgot-password/",
            {"email": "missing@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data.get("detail"), "No account exists for this email.")
