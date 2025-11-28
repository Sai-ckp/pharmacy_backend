from decimal import Decimal
from datetime import date as _date, timedelta

from django.db import transaction
from django.db.models import Sum, F
from rest_framework.exceptions import ValidationError

from .models import InventoryMovement
from apps.catalog.models import BatchLot, Product
from apps.locations.models import Location
from apps.settingsx.services import get_setting


def stock_on_hand(location_id: int, batch_lot_id: int) -> Decimal:
    agg = (
        InventoryMovement.objects.filter(location_id=location_id, batch_lot_id=batch_lot_id)
        .aggregate(total=Sum("qty_change_base"))
        .get("total")
    )
    return agg or Decimal("0")


def is_batch_sellable(batch_lot_id: int, on_date: _date | None = None) -> tuple[bool, str]:
    lot = BatchLot.objects.get(id=batch_lot_id)
    if lot.status in {BatchLot.Status.EXPIRED, BatchLot.Status.BLOCKED, BatchLot.Status.RETURNED}:
        return False, f"status={lot.status}"
    on_date = on_date or _date.today()
    try:
        critical_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
    except Exception:
        critical_days = 30
    cutoff = on_date + timedelta(days=critical_days)
    if lot.expiry_date and lot.expiry_date <= cutoff:
        return False, "expiry_within_critical_window"
    return True, "OK"


STRIP_NAMES = {"STRIP", "STRIPS"}
BOX_NAMES = {"BOX", "BOXES", "CARTON", "CARTONS"}


def convert_quantity_to_base(
    *,
    quantity: Decimal,
    base_uom,
    selling_uom,
    quantity_uom,
    units_per_pack: Decimal,
    tablets_per_strip: int | None = None,
    strips_per_box: int | None = None,
) -> tuple[Decimal, Decimal]:
    """
    Convert quantity expressed in quantity_uom into base units.
    Returns (base_quantity, factor_used).
    """
    if quantity < 0:
        raise ValidationError({"quantity": "Quantity must be >= 0"})
    if not quantity_uom:
        raise ValidationError({"quantity_uom": "Quantity unit is required"})
    if not base_uom:
        raise ValidationError({"base_uom": "Base unit is required"})
    if not selling_uom:
        raise ValidationError({"selling_uom": "Selling unit is required"})

    q_uom_name = (quantity_uom.name or "").strip().upper()
    base_name = (base_uom.name or "").strip().upper()

    if quantity_uom.id == base_uom.id:
        factor = Decimal("1")
    elif quantity_uom.id == selling_uom.id:
        factor = units_per_pack
    elif base_name in {"TAB", "TABLET", "CAP", "CAPSULE"} and q_uom_name in STRIP_NAMES:
        if not tablets_per_strip:
            raise ValidationError({"tablets_per_strip": "tablets_per_strip is required for STRIP quantities"})
        factor = Decimal(tablets_per_strip)
    elif base_name in {"TAB", "TABLET", "CAP", "CAPSULE"} and q_uom_name in BOX_NAMES:
        if not tablets_per_strip:
            raise ValidationError({"tablets_per_strip": "tablets_per_strip is required for BOX quantities"})
        if not strips_per_box:
            raise ValidationError({"strips_per_box": "strips_per_box is required for BOX quantities"})
        factor = Decimal(tablets_per_strip) * Decimal(strips_per_box)
    else:
        raise ValidationError({
            "quantity_uom": f"Cannot convert from {quantity_uom} to base unit {base_uom}. Provide units_per_pack."
        })

    if factor <= 0:
        raise ValidationError({"units_per_pack": "Conversion factor must be > 0"})
    return Decimal(quantity) * factor, factor


def stock_status_for_quantity(qty_base: Decimal, reorder_level: Decimal | None) -> str:
    if qty_base is None or qty_base <= 0:
        return "OUT_OF_STOCK"
    if reorder_level is not None and qty_base <= reorder_level:
        return "LOW_STOCK"
    return "IN_STOCK"

@transaction.atomic
def write_movement(
    location_id: int,
    batch_lot_id: int,
    qty_change_base: Decimal,
    *,
    reason: str,
    ref_doc: tuple[str, int],
    actor=None,
) -> int:

    # === Validate location ===
    try:
        location = Location.objects.select_for_update().get(id=location_id)
    except Location.DoesNotExist:
        raise ValidationError({
            "location_id": f"Invalid location_id '{location_id}'. Location does not exist."
        })

    # === Validate batch lot ===
    try:
        batch = BatchLot.objects.select_for_update().get(id=batch_lot_id)
    except BatchLot.DoesNotExist:
        raise ValidationError({
            "batch_lot_id": f"Invalid batch_lot_id '{batch_lot_id}'. Batch lot does not exist."
        })

    # === Negative stock logic ===
    allow_negative = (get_setting("ALLOW_NEGATIVE_STOCK", "false") or "false").lower() == "true"

    if not allow_negative and qty_change_base < 0:
        current = stock_on_hand(location_id, batch_lot_id)
        if current + Decimal(qty_change_base) < 0:
            raise ValidationError({
                "quantity": "Insufficient stock; negative stock not allowed."
            })

    # === Validate ref_doc structure ===
    if not isinstance(ref_doc, tuple) or len(ref_doc) != 2:
        raise ValidationError({
            "ref_doc": "ref_doc must be a tuple: (doc_type: str, doc_id: int)"
        })

    doc_type, doc_id = ref_doc
    if doc_id is not None:
        try:
            doc_id = int(doc_id)
        except ValueError:
            raise ValidationError({"ref_doc_id": "ref_doc_id must be an integer"})

    # === Create inventory movement ===
    mov = InventoryMovement.objects.create(
        location=location,
        batch_lot=batch,
        qty_change_base=Decimal(qty_change_base),
        reason=reason,
        ref_doc_type=doc_type,
        ref_doc_id=doc_id,
    )

    # === Audit logging (safe) ===
    try:
        from apps.governance.services import audit
        audit(
            actor,
            table="inventory_inventorymovement",
            row_id=mov.id,
            action="CREATE",
            before=None,
            after={
                "location_id": location.id,
                "batch_lot_id": batch.id,
                "qty_change_base": str(mov.qty_change_base),
                "reason": reason,
                "ref_doc_type": mov.ref_doc_type,
                "ref_doc_id": mov.ref_doc_id,
            },
        )
    except Exception:
        pass

    return mov.id


# Helper functions used by views
def stock_summary(location_id=None, product_id=None, batch_lot_id=None):
    qs = InventoryMovement.objects.all()
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
    if days is None:
        try:
            days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        except Exception:
            days = 60
    cutoff = _date.today() + timedelta(days=days)
    qs = InventoryMovement.objects.all()
    if location_id:
        qs = qs.filter(location_id=location_id)
    rows = (
        qs.values(
            "location_id",
            "batch_lot_id",
            batch_no=F("batch_lot__batch_no"),
            expiry_date=F("batch_lot__expiry_date"),
            product_id=F("batch_lot__product_id"),
        )
        .annotate(stock_base=Sum("qty_change_base"))
        .filter(expiry_date__isnull=False, expiry_date__lte=cutoff, stock_base__gt=0)
    )
    return list(rows)


def low_stock(location_id):
    # Aggregate by product and compare with thresholds
    agg = (
        InventoryMovement.objects.filter(location_id=location_id)
        .values("batch_lot__product_id")
        .annotate(stock_base=Sum("qty_change_base"))
    )
    product_ids = [r["batch_lot__product_id"] for r in agg]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
    try:
        default_low = Decimal(get_setting("ALERT_LOW_STOCK_DEFAULT", "50") or "50")
    except Exception:
        default_low = Decimal("50")
    result = []
    for r in agg:
        p = products.get(r["batch_lot__product_id"])
        if not p:
            continue
        threshold = p.reorder_level if p.reorder_level is not None else default_low
        if r["stock_base"] is not None and threshold is not None and r["stock_base"] <= threshold:
            result.append(
                {
                    "product_id": p.id,
                    "product_name": p.name,
                    "stock_base": r["stock_base"],
                    "reorder_level": threshold,
                    "location_id": location_id,
                }
            )
    return result


def inventory_stats(location_id: int) -> dict:
    from apps.catalog.models import Product
    # Sum stock by product at location
    agg = (
        InventoryMovement.objects.filter(location_id=location_id)
        .values("batch_lot__product_id")
        .annotate(stock_base=Sum("qty_change_base"))
    )
    product_ids = [r["batch_lot__product_id"] for r in agg]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
    try:
        default_low = Decimal(get_setting("ALERT_LOW_STOCK_DEFAULT", "50") or "50")
    except Exception:
        default_low = Decimal("50")
    counts = {"in_stock": 0, "low_stock": 0, "out_of_stock": 0}
    for r in agg:
        qty = r.get("stock_base") or Decimal("0")
        p = products.get(r["batch_lot__product_id"])
        threshold = p.reorder_level if p and p.reorder_level is not None else default_low
        if qty <= 0:
            counts["out_of_stock"] += 1
        elif qty <= threshold:
            counts["low_stock"] += 1
        else:
            counts["in_stock"] += 1
    return counts

