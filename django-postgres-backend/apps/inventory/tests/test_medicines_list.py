from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import ProductCategory, Product, MedicineForm, Uom, BatchLot
from apps.inventory.models import InventoryMovement, RackLocation
from apps.locations.models import Location


class MedicinesListViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="invtester", password="pass123", is_staff=True)
        self.client.force_authenticate(self.user)
        self.location = Location.objects.create(code="LOC1", name="Main")
        self.category = ProductCategory.objects.create(name="Analgesics")
        self.form = MedicineForm.objects.create(name="Tablet")
        self.uom_tab = Uom.objects.create(name="TAB")
        self.rack = RackLocation.objects.create(name="Rack A")

        self.product = Product.objects.create(
            code="P001",
            name="Paracetamol",
            category=self.category,
            medicine_form=self.form,
            mrp=Decimal("50.00"),
            base_unit="TAB",
            pack_unit="TAB",
            units_per_pack=Decimal("1.000"),
            base_unit_step=Decimal("1.000"),
            gst_percent=Decimal("5.00"),
            reorder_level=Decimal("5.000"),
            base_uom=self.uom_tab,
            selling_uom=self.uom_tab,
            rack_location=self.rack,
        )
        self.batch = BatchLot.objects.create(
            product=self.product,
            batch_no="B1",
            expiry_date=date.today() + timedelta(days=365),
            status=BatchLot.Status.ACTIVE,
        )
        InventoryMovement.objects.create(
            location=self.location,
            batch_lot=self.batch,
            qty_change_base=Decimal("10.000"),
            reason=InventoryMovement.Reason.PURCHASE,
            ref_doc_type="TEST",
            ref_doc_id=1,
        )

    def test_list_requires_location_and_returns_status(self):
        url = "/api/v1/inventory/medicines/"
        resp_missing = self.client.get(url)
        self.assertEqual(resp_missing.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.get(url, {"location_id": self.location.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["status"], "IN_STOCK")

    def test_filters_by_category_and_status(self):
        url = "/api/v1/inventory/medicines/"
        # Low stock scenario
        InventoryMovement.objects.create(
            location=self.location,
            batch_lot=self.batch,
            qty_change_base=Decimal("-8.000"),
            reason=InventoryMovement.Reason.ADJUSTMENT,
            ref_doc_type="TEST",
            ref_doc_id=2,
        )
        resp = self.client.get(url, {"location_id": self.location.id, "status": "LOW_STOCK"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["status"], "LOW_STOCK")

        resp_cat = self.client.get(
            url, {"location_id": self.location.id, "category_id": self.category.id}
        )
        self.assertEqual(resp_cat.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_cat.data), 1)

        resp_none = self.client.get(url, {"location_id": self.location.id, "category_id": 999})
        self.assertEqual(resp_none.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_none.data), 0)


class GlobalMedicinesViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="globaltester", password="pass123", is_staff=True)
        self.client.force_authenticate(self.user)
        self.location1 = Location.objects.create(code="LOC1", name="Main")
        self.location2 = Location.objects.create(code="LOC2", name="Branch")
        category = ProductCategory.objects.create(name="Antibiotics")
        form = MedicineForm.objects.create(name="Tablet")
        uom = Uom.objects.create(name="TAB")
        rack = RackLocation.objects.create(name="Rack B")
        self.product = Product.objects.create(
            code="PX100",
            name="DemoCaps",
            category=category,
            medicine_form=form,
            mrp=Decimal("100.00"),
            base_unit="TAB",
            pack_unit="TAB",
            units_per_pack=Decimal("1.000"),
            base_unit_step=Decimal("1.000"),
            gst_percent=Decimal("12.00"),
            reorder_level=Decimal("10.000"),
            base_uom=uom,
            selling_uom=uom,
            rack_location=rack,
        )
        self.batch = BatchLot.objects.create(
            product=self.product,
            batch_no="B-GLB",
            expiry_date=date.today() + timedelta(days=200),
            status=BatchLot.Status.ACTIVE,
        )
        InventoryMovement.objects.create(
            location=self.location1,
            batch_lot=self.batch,
            qty_change_base=Decimal("3.000"),
            reason=InventoryMovement.Reason.PURCHASE,
            ref_doc_type="TEST",
            ref_doc_id=1,
        )
        InventoryMovement.objects.create(
            location=self.location2,
            batch_lot=self.batch,
            qty_change_base=Decimal("4.000"),
            reason=InventoryMovement.Reason.PURCHASE,
            ref_doc_type="TEST",
            ref_doc_id=2,
        )

    def test_global_endpoint_sums_quantities(self):
        url = "/api/v1/inventory/medicines/global/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["quantity"], 7.0)
        self.assertEqual(resp.data[0]["status"], "LOW_STOCK")

    def test_global_endpoint_filters_by_status(self):
        url = "/api/v1/inventory/medicines/global/"
        resp = self.client.get(url, {"status": "IN_STOCK"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)

    def test_global_endpoint_filters_expiring(self):
        self.batch.expiry_date = date.today() + timedelta(days=5)
        self.batch.save(update_fields=["expiry_date"])
        url = "/api/v1/inventory/medicines/global/"
        resp = self.client.get(url, {"status": "EXPIRING"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertTrue(resp.data[0]["is_expiring"])


class MedicineDetailViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="detailtester", password="pass123", is_staff=True)
        self.client.force_authenticate(self.user)
        self.location = Location.objects.create(code="LOC3", name="Downtown")
        self.category = ProductCategory.objects.create(name="Supplements")
        self.form = MedicineForm.objects.create(name="Tablet")
        self.uom = Uom.objects.create(name="TAB")
        self.rack = RackLocation.objects.create(name="Rack Z")
        self.product = Product.objects.create(
            code="PX200",
            name="Vitamin C",
            category=self.category,
            medicine_form=self.form,
            mrp=Decimal("90.00"),
            base_unit="TAB",
            pack_unit="STRIP",
            units_per_pack=Decimal("10.000"),
            base_unit_step=Decimal("1.000"),
            gst_percent=Decimal("5.00"),
            reorder_level=Decimal("5.000"),
            base_uom=self.uom,
            selling_uom=self.uom,
            rack_location=self.rack,
            tablets_per_strip=10,
            strips_per_box=10,
        )
        self.batch = BatchLot.objects.create(
            product=self.product,
            batch_no="B-DTL",
            expiry_date=date.today() + timedelta(days=365),
            status=BatchLot.Status.ACTIVE,
            quantity_uom=self.uom,
            initial_quantity=Decimal("100.000"),
            initial_quantity_base=Decimal("100.000"),
            purchase_price=Decimal("500.00"),
            purchase_price_per_base=Decimal("5.00"),
        )
        InventoryMovement.objects.create(
            location=self.location,
            batch_lot=self.batch,
            qty_change_base=Decimal("100.000"),
            reason=InventoryMovement.Reason.PURCHASE,
            ref_doc_type="TEST",
            ref_doc_id=9,
        )

    def test_get_detail(self):
        url = f"/api/v1/inventory/medicines/{self.batch.id}/"
        resp = self.client.get(url, {"location_id": self.location.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["medicine"]["name"], "Vitamin C")
        self.assertEqual(resp.data["batch"]["batch_number"], "B-DTL")

    def test_put_updates_medicine_and_batch(self):
        url = f"/api/v1/inventory/medicines/{self.batch.id}/"
        payload = {
            "location_id": self.location.id,
            "medicine": {
                "id": self.product.id,
                "name": "Vitamin C Updated",
                "generic_name": "Ascorbic",
                "category": self.category.id,
                "form": self.form.id,
                "strength": "500 mg",
                "base_uom": self.uom.id,
                "selling_uom": self.uom.id,
                "rack_location": self.rack.id,
                "tablets_per_strip": 10,
                "strips_per_box": 10,
                "gst_percent": "5.00",
                "description": "",
                "reorder_level": 5,
                "mrp": "95.00",
            },
            "batch": {
                "id": self.batch.id,
                "batch_number": "B-DTL-2",
                "mfg_date": str(date.today()),
                "expiry_date": str(date.today() + timedelta(days=400)),
                "quantity": 120,
                "quantity_uom": self.uom.id,
                "purchase_price": "600.00",
            },
        }
        resp = self.client.put(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.product.name, "Vitamin C Updated")
        self.assertEqual(self.batch.batch_no, "B-DTL-2")

    def test_global_endpoint_filters_expiring(self):
        self.batch.expiry_date = date.today() + timedelta(days=5)
        self.batch.save(update_fields=["expiry_date"])
        url = "/api/v1/inventory/medicines/global/"
        resp = self.client.get(url, {"status": "EXPIRING"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertTrue(resp.data[0]["is_expiring"])
