from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from apps.catalog.models import ProductCategory
from apps.settingsx.models import PaymentMethod, PaymentTerm
from apps.inventory.models import RackLocation
from apps.catalog.models import MedicineForm, Uom


class MastersApiTests(APITestCase):
    def test_categories_crud_and_search(self):
        url = "/api/v1/catalog/categories/"
        r = self.client.post(url, {"name": "Antibiotics", "description": "AB", "is_active": True}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # duplicate (case-insensitive)
        r2 = self.client.post(url, {"name": "antibiotics"}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)
        # search
        r3 = self.client.get(url + "?q=anti")
        self.assertGreaterEqual(r3.data["count"], 1)

    def test_forms_uoms_methods_terms_racks(self):
        # forms
        r = self.client.post("/api/v1/catalog/forms/", {"name": "Capsule"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # uoms
        r = self.client.post("/api/v1/catalog/uoms/", {"name": "Strip", "uom_type": "PACK"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # payment methods
        r = self.client.post("/api/v1/settings/payment-methods/", {"name": "Cash"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # payment terms
        r = self.client.post("/api/v1/settings/payment-terms/", {"name": "Net 15", "days": 15}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        # rack locations
        r = self.client.post("/api/v1/inventory/rack-locations/", {"name": "A1"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_counts_endpoint(self):
        # seed a minimal row
        ProductCategory.objects.get_or_create(name="X")
        MedicineForm.objects.get_or_create(name="Y")
        Uom.objects.get_or_create(name="Z")
        PaymentMethod.objects.get_or_create(name="M")
        PaymentTerm.objects.get_or_create(name="T")
        RackLocation.objects.get_or_create(name="R")
        r = self.client.get("/api/v1/masters/counts/")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        for k in ["categories", "forms", "uoms", "payment_methods", "payment_terms", "rack_locations"]:
            self.assertIn(k, r.data)

