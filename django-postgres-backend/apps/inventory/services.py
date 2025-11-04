# Inventory ledger + helpers

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F

from .models import InventoryLedger
from apps.catalog.models import BatchLot, Product
from apps.locations.models import Location
from apps.settingsx.models import Settings


@transaction.atomic
def write_movement(location_id, batch_lot_id, qty_change_base, reason, ref_doc_type, ref_doc_id):
    location = Location.objects.select_for_update().get(id=location_id)
    batch = BatchLot.objects.select_for_update().get(id=batch_lot_id)
    return InventoryLedger.objects.create(
        location=location,
        batch_lot=batch,
        qty_change_base=Decimal(qty_change_base),
        reason=reason,
        ref_doc_type=ref_doc_type or "",
        ref_doc_id=ref_doc_id or "",
    )


def stock_on_hand(location_id, batch_lot_id):
    agg = (
        InventoryLedger.objects.filter(location_id=location_id, batch_lot_id=batch_lot_id)
        .aggregate(total=Sum("qty_change_base"))
        .get("total")
    )
    return agg or Decimal("0")


def stock_summary(location_id=None, product_id=None, batch_lot_id=None):
    qs = InventoryLedger.objects.all()
    if location_id:
        qs = qs.filter(location_id=location_id)
    if batch_lot_id:
        qs = qs.filter(batch_lot_id=batch_lot_id)
    if product_id:
        qs = qs.filter(batch_lot__product_id=product_id)
    rows = (
        qs.values("location_id", "batch_lot_id", product_id=F("batch_lot__product_id"))
        .annotate(stock_base=Sum("qty_change_base"))
    )
    return list(rows)


def near_expiry(days=None, location_id=None):
    from datetime import date, timedelta

    if days is None:
        try:
            days = int(Settings.objects.get(key="expiry_threshold_days").value)
        except Settings.DoesNotExist:
            days = 180
    cutoff = date.today() + timedelta(days=days)
    qs = InventoryLedger.objects.all()
    if location_id:
        qs = qs.filter(location_id=location_id)
    rows = (
        qs.values("location_id", "batch_lot_id", batch_no=F("batch_lot__batch_no"),
                  expiry_date=F("batch_lot__expiry_date"), product_id=F("batch_lot__product_id"))
        .annotate(stock_base=Sum("qty_change_base"))
        .filter(expiry_date__isnull=False, expiry_date__lte=cutoff, stock_base__gt=0)
    )
    return list(rows)


def low_stock(location_id):
    # Aggregate by product and compare with product.reorder_level
    agg = (
        InventoryLedger.objects.filter(location_id=location_id)
        .values("batch_lot__product_id")
        .annotate(stock_base=Sum("qty_change_base"))
    )
    product_ids = [r["batch_lot__product_id"] for r in agg]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
    result = []
    for r in agg:
        p = products.get(r["batch_lot__product_id"])
        if not p or p.reorder_level is None:
            continue
        if r["stock_base"] < p.reorder_level:
            result.append({
                "product_id": p.id,
                "product_name": p.name,
                "stock_base": r["stock_base"],
                "reorder_level": p.reorder_level,
                "location_id": location_id,
            })
    return result

