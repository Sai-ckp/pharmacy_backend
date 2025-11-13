from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


class PermissionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username="user", password="x")
        self.admin = get_user_model().objects.create_user(username="admin", password="x", is_superuser=True)

    def test_run_endpoints_require_admin(self):
        # unauth
        r = self.client.post("/api/v1/governance/run/expiry-scan")
        assert r.status_code in (401, 403)
        # non-admin
        self.client.force_authenticate(self.user)
        r = self.client.post("/api/v1/governance/run/expiry-scan")
        assert r.status_code == 403
        # admin
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/v1/governance/run/expiry-scan")
        assert r.status_code == 200

