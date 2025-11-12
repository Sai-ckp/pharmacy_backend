from django.test import TestCase
from apps.catalog.models import Product, ProductCategory, VendorProductCode
from apps.procurement.models import Vendor
from apps.catalog.services_vendor_map import product_by_vendor_code


class VendorMapTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="ACME")
        cat = ProductCategory.objects.create(name="C")
        self.p = Product.objects.create(
            code="ABC123", name="P", category=cat, hsn="", schedule="OTC",
            pack_size="1", manufacturer="M", mrp="1.00", base_unit="U", pack_unit="U", units_per_pack="1.000", base_unit_step="1.000", gst_percent="0", reorder_level="0.000",
        )

    def test_resolution_precedence(self):
        # product.code direct match
        assert product_by_vendor_code(self.vendor.id, "abc123").id == self.p.id
        # mapping fallback
        p2 = Product.objects.create(
            code="XYZ", name="P2", category=self.p.category, hsn="", schedule="OTC",
            pack_size="1", manufacturer="M", mrp="1.00", base_unit="U", pack_unit="U", units_per_pack="1.000", base_unit_step="1.000", gst_percent="0", reorder_level="0.000",
        )
        VendorProductCode.objects.create(vendor=self.vendor, product=p2, vendor_code="V-001")
        assert product_by_vendor_code(self.vendor.id, "V-001").id == p2.id

