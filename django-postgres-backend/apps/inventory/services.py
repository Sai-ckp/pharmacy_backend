from decimal import Decimal
from datetime import date as _date, timedelta

from django.db import transaction
from django.db.models import Sum, F
from rest_framework.exceptions import ValidationError

from .models import InventoryMovement
from apps.catalog.models import BatchLot, Product
from apps.locations.models import Location
from apps.settingsx.services import get_setting
from apps.settingsx.utils import get_stock_thresholds


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
BOX_NAMES = {"BOX", "BOXES", "CARTON", "CARTONS", "PACK", "PACKS"}
BOTTLE_NAMES = {"BOTTLE", "BOTTLES", "BOT", "BTS"}
TUBE_NAMES = {"TUBE", "TUBES"}
TAB_BASE_NAMES = {"TAB", "TABLET", "TABLETS", "CAP", "CAPS", "CAPSULE", "CAPSULES"}
ML_BASE_NAMES = {"ML", "MILLILITER", "MILLILITRE"}
VIAL_BASE_NAMES = {"VIAL", "VIALS", "AMP", "AMPOULE", "AMPOULES"}
GM_BASE_NAMES = {"GM", "GRAM", "GRAMS", "GMS", "GRM"}


def convert_quantity_to_base(
    *,
    quantity: Decimal,
    base_uom,
    selling_uom,
    quantity_uom,
    units_per_pack: Decimal,
    stock_unit: str | None = None,  # New: "box" or "loose"
    tablets_per_strip: int | None = None,
    capsules_per_strip: int | None = None,
    strips_per_box: int | None = None,
    ml_per_bottle: Decimal | None = None,
    bottles_per_box: int | None = None,
    ml_per_vial: Decimal | None = None,
    grams_per_tube: Decimal | None = None,
    tubes_per_box: int | None = None,
    vials_per_box: int | None = None,
    grams_per_sachet: Decimal | None = None,
    sachets_per_box: int | None = None,
    grams_per_bar: Decimal | None = None,
    bars_per_box: int | None = None,
    pieces_per_pack: int | None = None,
    packs_per_box: int | None = None,
    pairs_per_pack: int | None = None,
    grams_per_pack: Decimal | None = None,
    doses_per_inhaler: int | None = None,
    inhalers_per_box: int | None = None,
) -> tuple[Decimal, Decimal]:
    """
    Convert quantity expressed in quantity_uom into base units.
    Returns (base_quantity, factor_used).
    Note: quantity can be negative for stock reduction.
    """
    # Allow negative quantities for stock reduction
    is_negative = quantity < 0
    quantity_abs = abs(Decimal(quantity))
    
    # Helper function to apply sign to result
    def apply_sign(result, factor):
        return (-result if is_negative else result, factor)
    
    # If quantity_uom is not provided, infer from stock_unit and packaging fields
    if not quantity_uom:
        if stock_unit == "box":
            # For box, calculate from packaging fields
            # Tablet/Capsule
            if (tablets_per_strip or capsules_per_strip) and strips_per_box:
                per_strip = tablets_per_strip or capsules_per_strip
                factor = Decimal(per_strip) * Decimal(strips_per_box)
                result = quantity_abs * factor
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"convert_quantity_to_base: stock_unit=box, quantity={quantity_abs}, "
                           f"tablets_per_strip={per_strip}, strips_per_box={strips_per_box}, "
                           f"factor={factor}, result={result}")
                return apply_sign(result, factor)
            # Liquid (syrup, drops, spray, etc.)
            elif ml_per_bottle and bottles_per_box:
                factor = ml_per_bottle * Decimal(bottles_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Injection/Vial
            elif ml_per_vial and vials_per_box:
                factor = ml_per_vial * Decimal(vials_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            elif vials_per_box:
                factor = Decimal(vials_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Ointment/Cream/Gel
            elif grams_per_tube and tubes_per_box:
                factor = grams_per_tube * Decimal(tubes_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Powder/Sachet
            elif grams_per_sachet and sachets_per_box:
                factor = grams_per_sachet * Decimal(sachets_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Soap/Bar
            elif grams_per_bar and bars_per_box:
                factor = grams_per_bar * Decimal(bars_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Pack/Generic
            elif pieces_per_pack and packs_per_box:
                factor = Decimal(pieces_per_pack) * Decimal(packs_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Gloves
            elif pairs_per_pack and packs_per_box:
                factor = Decimal(pairs_per_pack) * Decimal(packs_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Cotton/Gauze
            elif grams_per_pack and packs_per_box:
                factor = grams_per_pack * Decimal(packs_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Inhaler
            elif doses_per_inhaler and inhalers_per_box:
                factor = Decimal(doses_per_inhaler) * Decimal(inhalers_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Fallback: use units_per_pack if available
            if units_per_pack and units_per_pack > 0:
                result = quantity_abs * units_per_pack
                return apply_sign(result, units_per_pack)
        
        elif stock_unit == "loose":
            # For loose, calculate from per-unit packaging fields
            # Tablet/Capsule
            if tablets_per_strip:
                factor = Decimal(tablets_per_strip)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            elif capsules_per_strip:
                factor = Decimal(capsules_per_strip)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Liquid
            elif ml_per_bottle:
                factor = ml_per_bottle
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Injection/Vial
            elif ml_per_vial:
                factor = ml_per_vial
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Ointment/Cream/Gel
            elif grams_per_tube:
                factor = grams_per_tube
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Powder/Sachet
            elif grams_per_sachet:
                factor = grams_per_sachet
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Soap/Bar
            elif grams_per_bar:
                factor = grams_per_bar
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Pack/Generic
            elif pieces_per_pack:
                factor = Decimal(pieces_per_pack)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Gloves
            elif pairs_per_pack:
                factor = Decimal(pairs_per_pack)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Cotton/Gauze
            elif grams_per_pack:
                factor = grams_per_pack
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Inhaler
            elif doses_per_inhaler:
                factor = Decimal(doses_per_inhaler)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Fallback: assume quantity is already in base units
            return apply_sign(quantity_abs, Decimal("1"))
        
        # If no stock_unit, try to infer from units_per_pack
        if units_per_pack and units_per_pack > 1 and selling_uom:
            quantity_uom = selling_uom
        elif base_uom:
            quantity_uom = base_uom
        else:
            # Last resort: use units_per_pack directly
            if units_per_pack and units_per_pack > 0:
                result = quantity_abs * units_per_pack
                return apply_sign(result, units_per_pack)
            return apply_sign(quantity_abs, Decimal("1"))
    
    # If quantity_uom is provided, check if we can use packaging fields directly
    # This handles the case where base_uom might not be set but we have packaging info
    if quantity_uom:
        q_uom_name = (quantity_uom.name or "").strip().upper()
        # If stock_unit is "box" and we have packaging fields, use them
        if stock_unit == "box":
            # Tablet/Capsule
            if (tablets_per_strip or capsules_per_strip) and strips_per_box:
                per_strip = tablets_per_strip or capsules_per_strip
                factor = Decimal(per_strip) * Decimal(strips_per_box)
                result = quantity_abs * factor
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"convert_quantity_to_base: Using packaging fields (quantity_uom provided), "
                           f"quantity={quantity_abs}, factor={factor}, result={result}")
                return apply_sign(result, factor)
            # Liquid (syrup, drops, spray, etc.)
            elif ml_per_bottle and bottles_per_box:
                factor = ml_per_bottle * Decimal(bottles_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Injection/Vial
            elif ml_per_vial and vials_per_box:
                factor = ml_per_vial * Decimal(vials_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            elif vials_per_box:
                factor = Decimal(vials_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Ointment/Cream/Gel
            elif grams_per_tube and tubes_per_box:
                factor = grams_per_tube * Decimal(tubes_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Powder/Sachet
            elif grams_per_sachet and sachets_per_box:
                factor = grams_per_sachet * Decimal(sachets_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Soap/Bar
            elif grams_per_bar and bars_per_box:
                factor = grams_per_bar * Decimal(bars_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Pack/Generic
            elif pieces_per_pack and packs_per_box:
                factor = Decimal(pieces_per_pack) * Decimal(packs_per_box)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Gloves
            elif pairs_per_pack:
                factor = Decimal(pairs_per_pack)
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Cotton/Gauze
            elif grams_per_pack:
                factor = grams_per_pack
                result = quantity_abs * factor
                return apply_sign(result, factor)
            # Inhaler
            elif doses_per_inhaler:
                factor = Decimal(doses_per_inhaler)
                result = quantity_abs * factor
                return apply_sign(result, factor)
    
    if not base_uom:
        # If no base_uom, assume quantity is already in base units
        return apply_sign(quantity_abs, Decimal("1"))
    
    if not selling_uom:
        # If no selling_uom, use base_uom
        selling_uom = base_uom

    q_uom_name = (quantity_uom.name or "").strip().upper()
    base_name = (base_uom.name or "").strip().upper()

    if quantity_uom.id == selling_uom.id:
        factor = units_per_pack
    elif quantity_uom.id == base_uom.id:
        factor = Decimal("1")
    elif base_name in TAB_BASE_NAMES and q_uom_name in STRIP_NAMES:
        if not tablets_per_strip:
            raise ValidationError({"tablets_per_strip": "tablets_per_strip is required for STRIP quantities"})
        factor = Decimal(tablets_per_strip)
    elif base_name in TAB_BASE_NAMES and q_uom_name in BOX_NAMES:
        if not tablets_per_strip:
            raise ValidationError({"tablets_per_strip": "tablets_per_strip is required for BOX quantities"})
        if not strips_per_box:
            raise ValidationError({"strips_per_box": "strips_per_box is required for BOX quantities"})
        factor = Decimal(tablets_per_strip) * Decimal(strips_per_box)
    elif base_name in ML_BASE_NAMES and q_uom_name in BOTTLE_NAMES:
        if not ml_per_bottle:
            raise ValidationError({"ml_per_bottle": "ml_per_bottle is required for bottle quantities"})
        factor = Decimal(ml_per_bottle)
    elif base_name in ML_BASE_NAMES and q_uom_name in BOX_NAMES:
        if not ml_per_bottle:
            raise ValidationError({"ml_per_bottle": "ml_per_bottle is required for box quantities"})
        if not bottles_per_box:
            raise ValidationError({"bottles_per_box": "bottles_per_box is required for box quantities"})
        factor = Decimal(ml_per_bottle) * Decimal(bottles_per_box)
    elif base_name in GM_BASE_NAMES and q_uom_name in TUBE_NAMES:
        if not grams_per_tube:
            raise ValidationError({"grams_per_tube": "grams_per_tube is required for tube quantities"})
        factor = Decimal(grams_per_tube)
    elif base_name in GM_BASE_NAMES and q_uom_name in BOX_NAMES:
        if not grams_per_tube:
            raise ValidationError({"grams_per_tube": "grams_per_tube is required for box quantities"})
        if not tubes_per_box:
            raise ValidationError({"tubes_per_box": "tubes_per_box is required for box quantities"})
        factor = Decimal(grams_per_tube) * Decimal(tubes_per_box)
    elif base_name in VIAL_BASE_NAMES and q_uom_name in BOX_NAMES:
        if not vials_per_box:
            raise ValidationError({"vials_per_box": "vials_per_box is required for box quantities"})
        factor = Decimal(vials_per_box)
    else:
        raise ValidationError({
            "quantity_uom": f"Cannot convert from {quantity_uom} to base unit {base_uom}. Provide units_per_pack."
        })

    if factor <= 0:
        raise ValidationError({"units_per_pack": "Conversion factor must be > 0"})
    result = quantity_abs * factor
    return apply_sign(result, factor)


def _resolve_thresholds() -> tuple[Decimal | None, Decimal | None]:
    low_default, critical_default = get_stock_thresholds()
    low_threshold = Decimal(str(low_default)) if low_default not in (None, "") else None
    critical_threshold = Decimal(str(critical_default)) if critical_default not in (None, "") else None
    return low_threshold, critical_threshold


def stock_status_for_quantity(qty_base: Decimal) -> str:
    if qty_base is None or qty_base <= 0:
        return "OUT_OF_STOCK"
    low_threshold, _ = _resolve_thresholds()
    if low_threshold is None:
        return "IN_STOCK"
    if qty_base <= low_threshold:
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
    product_map = {
        p.id: p.name for p in Product.objects.filter(id__in=product_ids).only("name")
    } if product_ids else {}
    low_default, _ = get_stock_thresholds()
    try:
        default_low = Decimal(str(low_default or 0))
    except Exception:
        default_low = Decimal("0")
    result = []
    for r in agg:
        threshold = default_low
        if threshold and r["stock_base"] is not None and r["stock_base"] <= threshold:
            result.append(
                {
                    "product_id": r["batch_lot__product_id"],
                    "product_name": product_map.get(r["batch_lot__product_id"], ""),
                    "stock_base": r["stock_base"],
                    "threshold": threshold,
                    "location_id": location_id,
                }
            )
    return result


def global_inventory_rows(
    *,
    search: str | None = None,
    category_id: int | None = None,
    rack_id: int | None = None,
    status: str | None = None,
    location_id: int | None = None,
) -> list[dict]:
    low_default, _ = get_stock_thresholds()
    try:
        default_threshold = Decimal(str(low_default or 0))
    except Exception:
        default_threshold = Decimal("0")

    try:
        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
    except Exception:
        warn_days = 60
    expiry_cutoff = _date.today() + timedelta(days=warn_days)

    qs = (
        InventoryMovement.objects.select_related(
            "batch_lot",
            "batch_lot__product",
            "batch_lot__product__category",
            "batch_lot__product__rack_location",
            "batch_lot__product__base_uom",
        )
        .filter(
            batch_lot__product__is_active=True,
            batch_lot__status=BatchLot.Status.ACTIVE,
        )
    )
    if location_id:
        qs = qs.filter(location_id=location_id)
    if category_id:
        qs = qs.filter(batch_lot__product__category_id=category_id)
    if rack_id:
        qs = qs.filter(batch_lot__product__rack_location_id=rack_id)
    if search:
        from django.db.models import Q

        search = search.strip()
        if search:
            qs = qs.filter(
                Q(batch_lot__product__name__icontains=search)
                | Q(batch_lot__product__code__icontains=search)
                | Q(batch_lot__batch_no__icontains=search)
                | Q(batch_lot__product__generic_name__icontains=search)
            )

    grouped = (
        qs.values(
            "batch_lot_id",
            "batch_lot__batch_no",
            "batch_lot__expiry_date",
            "batch_lot__rack_no",
            "batch_lot__product__id",
            "batch_lot__product__code",
            "batch_lot__product__name",
            "batch_lot__product__generic_name",
            "batch_lot__product__category__name",
            "batch_lot__product__category_id",
            "batch_lot__product__mrp",
            "batch_lot__product__base_uom__name",
            "batch_lot__product__rack_location__name",
            "batch_lot__product__rack_location_id",
        )
        .annotate(total_qty=Sum("qty_change_base"))
    )

    status_filter = (status or "").upper()
    results: list[dict] = []
    for row in grouped:
        qty = Decimal(row.get("total_qty") or 0)
        status_txt = stock_status_for_quantity(qty)

        expiry_date = row.get("batch_lot__expiry_date")
        is_expiring = bool(
            expiry_date
            and isinstance(expiry_date, _date)
            and expiry_date >= _date.today()
            and expiry_date <= expiry_cutoff
        )

        if status_filter == "EXPIRING":
            if not is_expiring:
                continue
        elif status_filter and status_txt != status_filter:
            continue
        rack_name = row.get("batch_lot__product__rack_location__name") or row.get("batch_lot__rack_no") or ""
        results.append(
            {
                "batch_id": row["batch_lot_id"],
                "medicine_id": row.get("batch_lot__product__code"),
                "product_id": row.get("batch_lot__product__id"),
                "batch_number": row.get("batch_lot__batch_no"),
                "medicine_name": row.get("batch_lot__product__name"),
                "category": row.get("batch_lot__product__category__name") or "",
                "category_id": row.get("batch_lot__product__category_id"),
                "quantity": float(qty),
                "uom": row.get("batch_lot__product__base_uom__name"),
                "rack": rack_name,
                "mrp": float(row.get("batch_lot__product__mrp") or 0),
                "expiry_date": row.get("batch_lot__expiry_date"),
                "status": status_txt,
                "is_expiring": is_expiring,
            }
        )
    return results


def inventory_stats(location_id: int) -> dict:
    from apps.catalog.models import Product
    # Sum stock by product at location
    agg = (
        InventoryMovement.objects.filter(location_id=location_id)
        .values("batch_lot__product_id")
        .annotate(stock_base=Sum("qty_change_base"))
    )
    product_ids = [r["batch_lot__product_id"] for r in agg]
    low_default, _ = get_stock_thresholds()
    try:
        default_low = Decimal(str(low_default or 50))
    except Exception:
        default_low = Decimal("50")
    counts = {"in_stock": 0, "low_stock": 0, "out_of_stock": 0}
    for r in agg:
        qty = r.get("stock_base") or Decimal("0")
        threshold = default_low
        if qty <= 0:
            counts["out_of_stock"] += 1
        elif threshold and qty <= threshold:
            counts["low_stock"] += 1
        else:
            counts["in_stock"] += 1
    return counts

