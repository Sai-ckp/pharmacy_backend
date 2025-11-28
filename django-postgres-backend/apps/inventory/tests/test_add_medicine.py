from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductCategory, MedicineForm, BatchLot, Uom
from apps.inventory.models import InventoryMovement, RackLocation
from apps.locations.models import Location


class AddMedicineAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="admin", email="admin@example.com", password="test123", is_staff=True, is_superuser=True
        )
        self.client.force_authenticate(self.user)
        self.location = Location.objects.create(code="LOC1", name="Main Store")
        self.category = ProductCategory.objects.create(name="Analgesics")
        self.form = MedicineForm.objects.create(name="Tablet")
        self.tab_uom = Uom.objects.create(name="TAB")
        self.strip_uom = Uom.objects.create(name="STRIP")
        self.box_uom = Uom.objects.create(name="BOX")
        self.rack = RackLocation.objects.create(name="Rack A")
        self.url = "/api/v1/inventory/add-medicine/"

    def test_add_medicine_creates_batch_and_stock_with_conversion(self):
        payload = self._payload(quantity_uom=self.box_uom.id)
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        product = Product.objects.get(name="Paracetamol 500mg")
        self.assertEqual(product.base_uom_id, self.tab_uom.id)
        self.assertEqual(product.selling_uom_id, self.strip_uom.id)
        self.assertEqual(product.rack_location_id, self.rack.id)

        batch = BatchLot.objects.get(product=product)
        self.assertEqual(batch.quantity_uom_id, self.box_uom.id)
        self.assertEqual(batch.initial_quantity, Decimal("5"))
        self.assertEqual(batch.initial_quantity_base, Decimal("250.000"))
        self.assertEqual(batch.purchase_price_per_base.quantize(Decimal("0.000001")), Decimal("0.700000"))

        movement = InventoryMovement.objects.filter(batch_lot=batch, location=self.location).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.qty_change_base, Decimal("250.000"))

        self.assertEqual(resp.data["batch"]["base_quantity"], "250.000")
        self.assertEqual(resp.data["inventory"]["stock_on_hand_base"], "250.000")
        self.assertEqual(resp.data["inventory"]["stock_status"], "IN_STOCK")

    def test_validation_for_missing_tablet_packaging(self):
        payload = self._payload(quantity_uom=self.box_uom.id)
        payload["medicine"].pop("tablets_per_strip")
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tablets_per_strip", str(resp.data))

    def test_invalid_master_ids_are_rejected(self):
        payload = self._payload(quantity_uom=self.box_uom.id)
        payload["medicine"]["rack_location"] = 9999
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rack_location", str(resp.data))

    def _payload(self, quantity_uom: int) -> dict:
        today = date.today()
        return {
            "location_id": self.location.id,
            "medicine": {
                "name": "Paracetamol 500mg",
                "generic_name": "Acetaminophen",
                "category": self.category.id,
                "form": self.form.id,
                "strength": "500 mg",
                "base_uom": self.tab_uom.id,
                "selling_uom": self.strip_uom.id,
                "rack_location": self.rack.id,
                "tablets_per_strip": 10,
                "strips_per_box": 5,
                "gst_percent": "5.00",
                "reorder_level": 50,
                "mrp": "35.00",
                "description": "Pain reliever",
                "storage_instructions": "Store away from sunlight",
            },
            "batch": {
                "batch_number": "PX-001",
                "mfg_date": (today - timedelta(days=30)).isoformat(),
                "expiry_date": (today + timedelta(days=365)).isoformat(),
                "quantity": 5,
                "quantity_uom": quantity_uom,
                "purchase_price": "35.00",
            },
        }
