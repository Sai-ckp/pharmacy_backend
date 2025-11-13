from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sales.models import SalesInvoice, SalesLine
from apps.sales.services import post_invoice
from apps.catalog.models import Product, BatchLot
from apps.locations.models import Location
from apps.inventory.models import InventoryMovement
from apps.compliance.models import H1RegisterEntry, NDPSDailyEntry
from apps.compliance.services import ensure_prescription_for_invoice, recompute_ndps_daily
from django.core.exceptions import ValidationError


class Testcompliance(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="admin")
        self.loc = Location.objects.create(name="Main")

        self.h1_product = Product.objects.create(name="H1 Drug", schedule="H1")
        self.ndps_product = Product.objects.create(name="NDPS Drug", schedule="NDPS")
        self.batch = BatchLot.objects.create(
            product=self.h1_product,
            batch_no="H1B001",
            expiry=timezone.now().date()
        )

        InventoryMovement.objects.create(location=self.loc, batch_lot=self.batch, qty_change_base=100)

        self.inv = SalesInvoice.objects.create(
            invoice_no="RX-001",
            location=self.loc,
            customer_id=None,
            created_by=self.user,
        )

        SalesLine.objects.create(
            sale_invoice=self.inv,
            product=self.h1_product,
            batch_lot=self.batch,
            qty_base=5,
            sold_uom="BASE",
            rate_per_base=10,
        )

    def test_prescription_required(self):
        with self.assertRaises(ValidationError):
            ensure_prescription_for_invoice(self.inv)

    def test_h1_entry_created(self):
        self.inv.prescription_id = None  # simulate valid prescription
        post_invoice(actor=self.user, invoice_id=self.inv.id)
        self.assertTrue(H1RegisterEntry.objects.exists())

    def test_ndps_recompute(self):
        NDPSDailyEntry.objects.create(
            product=self.h1_product,
            date=timezone.now().date(),
            opening_qty_base=50,
            in_qty_base=0,
            out_qty_base=10,
            closing_qty_base=40,
        )
        recompute_ndps_daily(self.h1_product.id, timezone.now().date(), timezone.now().date())
        obj = NDPSDailyEntry.objects.first()
        self.assertEqual(obj.closing_qty_base, 40)
