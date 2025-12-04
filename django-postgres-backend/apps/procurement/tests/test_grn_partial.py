from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import ProductCategory, Product, MedicineForm, Uom, BatchLot
from apps.inventory.models import InventoryMovement, RackLocation
from apps.locations.models import Location
from apps.procurement.models import Vendor, PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine
from apps.procurement.services import post_goods_receipt
from django.db import models


class GRNPartialTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username="grnuser", password="pass123", is_staff=True)
        self.client.force_authenticate(self.user)
        self.location = Location.objects.create(code="LOC1", name="Main")
        self.vendor = Vendor.objects.create(name="Acme")
        self.category = ProductCategory.objects.create(name="Analgesics")
        self.form = MedicineForm.objects.create(name="Tablet")
        self.uom = Uom.objects.create(name="TAB")
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
            base_uom=self.uom,
            selling_uom=self.uom,
            rack_location=self.rack,
        )

    def test_partial_receiving_updates_status_and_stock(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            location=self.location,
            po_number="PO-1",
            status=PurchaseOrder.Status.OPEN,
        )
        pol = PurchaseOrderLine.objects.create(
            po=po,
            product=self.product,
            requested_name="Paracetamol",
            qty_packs_ordered=100,
            expected_unit_cost=Decimal("5.00"),
        )
        grn = GoodsReceipt.objects.create(po=po, location=self.location, status=GoodsReceipt.Status.DRAFT)
        GoodsReceiptLine.objects.create(
            grn=grn,
            po_line=pol,
            product=self.product,
            batch_no="B1",
            mfg_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            qty_packs_received=50,
            qty_base_received=Decimal("50.000"),
            unit_cost=Decimal("5.00"),
            mrp=Decimal("50.00"),
        )

        post_goods_receipt(grn.id, actor=self.user)

        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)

        # Add second GRN to complete
        grn2 = GoodsReceipt.objects.create(po=po, location=self.location, status=GoodsReceipt.Status.DRAFT)
        GoodsReceiptLine.objects.create(
            grn=grn2,
            po_line=pol,
            product=self.product,
            batch_no="B1",
            mfg_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            qty_packs_received=50,
            qty_base_received=Decimal("50.000"),
            unit_cost=Decimal("5.00"),
            mrp=Decimal("50.00"),
        )
        post_goods_receipt(grn2.id, actor=self.user)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.COMPLETED)

        stock = InventoryMovement.objects.filter(location=self.location, batch_lot__batch_no="B1").aggregate(total_sum=models.Sum("qty_change_base"))
        self.assertEqual(Decimal(stock["total_sum"] or 0), Decimal("100.000"))

    def test_receiving_more_than_ordered_raises_error(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            location=self.location,
            po_number="PO-2",
            status=PurchaseOrder.Status.OPEN,
        )
        pol = PurchaseOrderLine.objects.create(
            po=po,
            product=self.product,
            requested_name="Paracetamol",
            qty_packs_ordered=24,
            expected_unit_cost=Decimal("5.00"),
        )

        grn = GoodsReceipt.objects.create(po=po, location=self.location, status=GoodsReceipt.Status.DRAFT)
        GoodsReceiptLine.objects.create(
            grn=grn,
            po_line=pol,
            product=self.product,
            batch_no="B2",
            mfg_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            qty_packs_received=12,
            qty_base_received=Decimal("12.000"),
            unit_cost=Decimal("5.00"),
            mrp=Decimal("50.00"),
        )
        post_goods_receipt(grn.id, actor=self.user)

        grn2 = GoodsReceipt.objects.create(po=po, location=self.location, status=GoodsReceipt.Status.DRAFT)
        GoodsReceiptLine.objects.create(
            grn=grn2,
            po_line=pol,
            product=self.product,
            batch_no="B2",
            mfg_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            qty_packs_received=13,
            qty_base_received=Decimal("13.000"),
            unit_cost=Decimal("5.00"),
            mrp=Decimal("50.00"),
        )
        with self.assertRaisesMessage(ValueError, "exceeds total ordered"):
            post_goods_receipt(grn2.id, actor=self.user)
        self.assertEqual(InventoryMovement.objects.count(), 1)

    def test_goods_receipt_updates_product_mrp_and_batch_prices(self):
        po = PurchaseOrder.objects.create(
            vendor=self.vendor,
            location=self.location,
            po_number="PO-3",
            status=PurchaseOrder.Status.OPEN,
        )
        pol = PurchaseOrderLine.objects.create(
            po=po,
            product=self.product,
            requested_name="Paracetamol",
            qty_packs_ordered=30,
            expected_unit_cost=Decimal("5.00"),
        )

        grn = GoodsReceipt.objects.create(po=po, location=self.location, status=GoodsReceipt.Status.DRAFT)
        GoodsReceiptLine.objects.create(
            grn=grn,
            po_line=pol,
            product=self.product,
            batch_no="B3",
            mfg_date=date.today(),
            expiry_date=date.today() + timedelta(days=365),
            qty_packs_received=10,
            qty_base_received=Decimal("10.000"),
            unit_cost=Decimal("6.00"),
            mrp=Decimal("75.00"),
        )

        post_goods_receipt(grn.id, actor=self.user)

        self.product.refresh_from_db()
        self.assertEqual(self.product.mrp, Decimal("75.00"))

        batch = BatchLot.objects.get(product=self.product, batch_no="B3")
        self.assertEqual(batch.purchase_price, Decimal("6.00"))
        self.assertEqual(batch.purchase_price_per_base, Decimal("6.000000"))
        self.assertEqual(batch.initial_quantity, Decimal("10.000"))
        self.assertEqual(batch.initial_quantity_base, Decimal("10.000"))
