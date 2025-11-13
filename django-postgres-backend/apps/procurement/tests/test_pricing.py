from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.procurement.services_pricing import compute_po_line_totals
from apps.procurement.models import PurchaseOrder, PurchaseOrderLine, Vendor
from apps.catalog.models import Product, ProductCategory
from apps.locations.models import Location


class PricingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.loc = Location.objects.create(code="LOC1", name="Main")
        self.vendor = Vendor.objects.create(name="Acme")
        cat = ProductCategory.objects.create(name="X")
        self.p1 = Product.objects.create(
            code="P1", name="Prod1", category=cat, hsn="", schedule="OTC",
            pack_size="1x10", manufacturer="M1", mrp=Decimal("100.00"),
            base_unit="TAB", pack_unit="STRIP", units_per_pack=Decimal("10.000"), base_unit_step=Decimal("1.000"),
            gst_percent=Decimal("12.00"), reorder_level=Decimal("0.000"), is_sensitive=False, is_active=True,
        )
        self.p2 = Product.objects.create(
            code="P2", name="Prod2", category=cat, hsn="", schedule="OTC",
            pack_size="1x1", manufacturer="M2", mrp=Decimal("50.00"),
            base_unit="BOT", pack_unit="BOT", units_per_pack=Decimal("1.000"), base_unit_step=Decimal("1.000"),
            gst_percent=Decimal("5.00"), reorder_level=Decimal("0.000"), is_sensitive=False, is_active=True,
        )

    def test_compute_helper(self):
        out = compute_po_line_totals(qty_packs=Decimal("2"), unit_cost_pack=Decimal("45"), product_gst_percent=Decimal("12"), gst_override=None)
        assert out["gross"] == Decimal("90.00") and out["tax"] == Decimal("10.80") and out["pct"] == Decimal("12")

    def test_po_create_recomputes_totals(self):
        url = "/api/v1/procurement/purchase-orders/"
        body = {
            "vendor": self.vendor.id,
            "location": self.loc.id,
            "lines": [
                {"product": self.p1.id, "qty_packs_ordered": 2, "expected_unit_cost": "45.00", "gst_percent_override": "12"},
                {"product": self.p2.id, "qty_packs_ordered": 1, "expected_unit_cost": "20.00"},
            ],
            "gross_total": "0.00",  # should be ignored
            "tax_total": "0.00",
            "net_total": "0.00",
        }
        r = self.client.post(url, body, format="json")
        assert r.status_code in (200, 201), r.data
        po = PurchaseOrder.objects.get(id=r.data.get("id", 1))
        assert po.gross_total > 0 and po.net_total == po.gross_total + po.tax_total

    def test_po_update_recomputes(self):
        # create minimal
        po = PurchaseOrder.objects.create(vendor=self.vendor, location=self.loc, po_number="PO-1")
        PurchaseOrderLine.objects.create(po=po, product=self.p1, qty_packs_ordered=1, expected_unit_cost=Decimal("10.00"))
        data = {"lines": [{"product": self.p1.id, "qty_packs_ordered": 3, "expected_unit_cost": "10.00"}]}
        url = f"/api/v1/procurement/purchase-orders/{po.id}/"
        r = self.client.patch(url, data, format="json")
        po.refresh_from_db()
        assert po.gross_total == Decimal("30.00")

