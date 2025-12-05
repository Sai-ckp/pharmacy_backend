from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from django.db import connection
from apps.locations.models import Location
from apps.procurement.models import Vendor, PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine
from apps.inventory.models import RackLocation
from apps.catalog.models import ProductCategory, MedicineForm, Uom
from apps.inventory.views import AddMedicineView, ExpiryAlertsView
from apps.inventory.services import stock_on_hand
from apps.procurement.services import post_goods_receipt
from apps.sales.views import SalesInvoiceViewSet
from apps.sales.models import SalesInvoice
from apps.settingsx.models import AlertThresholds
from apps.accounts.models import User as AccountsUser

factory = APIRequestFactory()
User = get_user_model()
admin, _ = User.objects.get_or_create(
    username="demo_admin",
    defaults={"email": "demo_admin@example.com", "is_staff": True, "is_superuser": True},
)
if not admin.is_staff:
    admin.is_staff = True
    admin.is_superuser = True
    admin.save(update_fields=["is_staff", "is_superuser"])
ops_user, _ = AccountsUser.objects.get_or_create(
    email="ops-demo@example.com",
    defaults={"full_name": "Ops Demo"},
)
accounts_admin, _ = AccountsUser.objects.update_or_create(
    id=admin.id,
    defaults={
        "email": admin.email or f"{admin.username}@demo.local",
        "full_name": getattr(admin, "get_full_name", lambda: "")() or admin.username,
    },
)
with connection.cursor() as cursor:
    cursor.execute(
        "SELECT setval(pg_get_serial_sequence('accounts_user','id'), (SELECT COALESCE(MAX(id),1) FROM accounts_user))"
    )

suffix = timezone.now().strftime("%Y%m%d%H%M%S")
location, _ = Location.objects.get_or_create(
    code=f"LOC-DEMO-{suffix}",
    defaults={"name": f"Demo Pharmacy {suffix}"},
)
vendor, _ = Vendor.objects.get_or_create(
    name=f"Acme Pharma {suffix}",
    defaults={"supplier_type": Vendor.SupplierType.OFFLINE},
)
category, _ = ProductCategory.objects.get_or_create(name="Antibiotics")
form_tab, _ = MedicineForm.objects.get_or_create(name="Tablet")
uom_tab, _ = Uom.objects.get_or_create(name="TAB", defaults={"uom_type": Uom.UomType.BASE})
uom_strip, _ = Uom.objects.get_or_create(name="STRIP", defaults={"uom_type": Uom.UomType.PACK})
uom_box, _ = Uom.objects.get_or_create(name="BOX", defaults={"uom_type": Uom.UomType.PACK})
rack, _ = RackLocation.objects.get_or_create(name=f"Rack Demo {suffix}")
product_name = f"Demo Amoxicillin 500-{suffix[-4:]}"
batch_seed = f"BATCH-DEMO-{suffix}"
customer_name = f"Test Walkin {suffix[-4:]}"

add_payload = {
    "location_id": location.id,
    "medicine": {
        "name": product_name,
        "generic_name": "Amoxicillin",
        "category": category.id,
        "form": form_tab.id,
        "strength": "500 mg",
        "base_uom": uom_tab.id,
        "selling_uom": uom_strip.id,
        "rack_location": rack.id,
        "tablets_per_strip": 10,
        "strips_per_box": 5,
        "gst_percent": "12.00",
        "reorder_level": 100,
        "mrp": "150.00",
        "description": "Test batch",
    },
    "batch": {
        "batch_number": f"{batch_seed}-001",
        "mfg_date": (timezone.now().date().replace(day=1)).isoformat(),
        "expiry_date": (
            timezone.now()
            .date()
            .replace(day=1)
            .replace(year=timezone.now().date().year + 1)
            .isoformat()
        ),
        "quantity": 3,
        "quantity_uom": uom_box.id,
        "purchase_price": "400.00",
    },
}
request = factory.post("/api/v1/inventory/add-medicine/", add_payload, format="json")
force_authenticate(request, user=admin)
response = AddMedicineView.as_view()(request)
response.render()
if response.status_code != 201:
    raise SystemExit(f"Add medicine failed: {response.status_code} {response.data}")
product_id = response.data["medicine"]["id"]
batch_id = response.data["batch"]["id"]

po = PurchaseOrder.objects.create(
    vendor=vendor,
    location=location,
    po_number=f"PO-DEMO-{suffix}",
    status=PurchaseOrder.Status.OPEN,
)
pol = PurchaseOrderLine.objects.create(
    po=po,
    requested_name="Demo Amoxicillin",
    qty_packs_ordered=40,
    expected_unit_cost=Decimal("120.00"),
)

# Partial GRN
partial_grn = GoodsReceipt.objects.create(po=po, location=location, status=GoodsReceipt.Status.DRAFT)
GoodsReceiptLine.objects.create(
    grn=partial_grn,
    po_line=pol,
    product_id=product_id,
    batch_no=f"{batch_seed}-002",
    mfg_date=timezone.now().date(),
    expiry_date=timezone.now()
    .date()
    .replace(month=max(1, timezone.now().date().month - 1), year=timezone.now().date().year + 1),
    qty_packs_received=20,
    qty_base_received=Decimal("200.000"),
    unit_cost=Decimal("120.00"),
    mrp=Decimal("150.00"),
)
post_goods_receipt(partial_grn.id, actor=ops_user)

# Final GRN
final_grn = GoodsReceipt.objects.create(po=po, location=location, status=GoodsReceipt.Status.DRAFT)
GoodsReceiptLine.objects.create(
    grn=final_grn,
    po_line=pol,
    product_id=product_id,
    batch_no=f"{batch_seed}-003",
    mfg_date=timezone.now().date(),
    expiry_date=timezone.now().date().replace(year=timezone.now().date().year + 2),
    qty_packs_received=20,
    qty_base_received=Decimal("200.000"),
    unit_cost=Decimal("120.00"),
    mrp=Decimal("150.00"),
)
post_goods_receipt(final_grn.id, actor=ops_user)

invoice_payload = {
    "location": location.id,
    "invoice_date": timezone.now().strftime("%d-%m-%Y %H:%M"),
    "lines": [
        {
            "product": product_id,
            "batch_lot": batch_id,
            "qty_base": "50.000",
            "sold_uom": "BASE",
            "rate_per_base": "2.50",
            "discount_amount": "0",
            "tax_percent": "12",
        }
    ],
    "customer_name": customer_name,
    "customer_phone": "9990011001",
    "customer_city": "DemoCity",
    "customer_billing_address": "12 Demo St",
}
request = factory.post("/api/v1/sales/invoices/", invoice_payload, format="json")
force_authenticate(request, user=admin)
response = SalesInvoiceViewSet.as_view({"post": "create"})(request)
response.render()
if response.status_code not in (200, 201):
    raise SystemExit(f"Invoice create failed: {response.status_code} {response.data}")
invoice_id = response.data["id"]

# Post the invoice to deduct stock
request = factory.post(f"/api/v1/sales/invoices/{invoice_id}/post/")
force_authenticate(request, user=admin)
post_resp = SalesInvoiceViewSet.as_view({"post": "post_invoice"})(request, pk=invoice_id)
post_resp.render()
if post_resp.status_code != 200:
    raise SystemExit(f"Invoice post failed: {post_resp.status_code} {post_resp.data}")

# Update alert thresholds and fetch expiry alerts
AlertThresholds.objects.update_or_create(
    id=1, defaults={"critical_expiry_days": 400, "warning_expiry_days": 800, "low_stock_default": 30}
)
request = factory.get(f"/api/v1/inventory/expiry-alerts/?location_id={location.id}")
force_authenticate(request, user=admin)
expiry_resp = ExpiryAlertsView.as_view()(request)
expiry_resp.render()

stock_summary = stock_on_hand(location.id, batch_id)
po.refresh_from_db()
partial_grn.refresh_from_db()
final_grn.refresh_from_db()

print(
    {
        "location": {"id": location.id, "code": location.code, "name": location.name},
        "vendor": {"id": vendor.id, "name": vendor.name},
        "product": {"id": product_id, "name": product_name},
        "batches": [
            {"id": batch_id, "batch_no": f"{batch_seed}-001"},
            {"batch_no": f"{batch_seed}-002"},
            {"batch_no": f"{batch_seed}-003"},
        ],
        "purchase_order": {"id": po.id, "number": po.po_number, "status": po.status},
        "goods_receipts": {
            "partial": {"id": partial_grn.id, "status": partial_grn.status},
            "final": {"id": final_grn.id, "status": final_grn.status},
        },
        "sales_invoice": {"id": invoice_id, "status": SalesInvoice.objects.get(id=invoice_id).status},
        "current_stock_base": str(stock_summary),
        "expiry_alerts": expiry_resp.data,
    }
)
