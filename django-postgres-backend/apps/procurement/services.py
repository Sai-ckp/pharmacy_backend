from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import BatchLot, Product, ProductCategory
from apps.catalog.services import packs_to_base
from apps.inventory.services import write_movement, convert_quantity_to_base
from apps.inventory.models import RackRule
from .models import (
    Purchase, PurchaseLine, VendorReturn, GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine,
)
from apps.governance.services import audit, emit_event
from django.utils import timezone

PRICE_PER_BASE_QUANT = Decimal("0.000001")

PRICE_PER_BASE_QUANT = Decimal("0.000001")


def assign_rack(location_id: int, manufacturer_name: str) -> str | None:
    rule = RackRule.objects.filter(location_id=location_id, manufacturer_name__iexact=manufacturer_name, is_active=True).first()
    return rule.rack_code if rule else None


@transaction.atomic
def post_purchase(purchase_id, actor=None):
    # Legacy flow: write purchase into stock
    p = Purchase.objects.select_for_update().get(id=purchase_id)
    total = Decimal("0")
    for line in p.lines.select_related("product"):
        product: Product = line.product
        received = Decimal(line.qty_packs) * (product.units_per_pack or Decimal("0"))
        line.received_base_qty = received
        line.save(update_fields=["received_base_qty"])

        batch, _ = BatchLot.objects.get_or_create(
            product=product,
            batch_no=line.batch_no,
            defaults={"expiry_date": line.expiry_date, "status": BatchLot.Status.ACTIVE},
        )
        write_movement(
            location_id=p.location_id,
            batch_lot_id=batch.id,
            qty_change_base=received,
            reason="PURCHASE",
            ref_doc=("PURCHASE", p.id),
            actor=actor,
        )
        total += (line.unit_cost * Decimal(line.qty_packs))

    p.gross_total = total
    p.net_total = total
    p.save(update_fields=["gross_total", "net_total"])

    audit(
        actor,
        table="procurement_purchase",
        row_id=p.id,
        action="POST_PURCHASE",
        before=None,
        after={"gross_total": str(p.gross_total)},
    )
    return p


@transaction.atomic
def post_goods_receipt(grn_id: int, actor) -> None:
    grn = (
        GoodsReceipt.objects.select_for_update()
        .select_related("po")
        .prefetch_related("lines__product", "po__lines")
        .get(id=grn_id)
    )
    if grn.status == GoodsReceipt.Status.POSTED:
        raise ValueError("GRN already POSTED")

    lines = list(grn.lines.select_related("po_line").all())
    if not lines:
        raise ValueError("Cannot POST an empty GRN.")

    per_line_received = defaultdict(lambda: Decimal("0"))
    po_line_map: dict[int, PurchaseOrderLine] = {}
    for ln in lines:
        if not ln.expiry_date or (ln.qty_packs_received or 0) <= 0:
            raise ValueError("Each GRN line must have expiry_date and qty_packs_received > 0")
        if not ln.po_line_id:
            raise ValueError("Each GRN line must be linked to a purchase order line.")
        qty_packs = Decimal(str(ln.qty_packs_received or 0))
        per_line_received[ln.po_line_id] += qty_packs
        po_line_map[ln.po_line_id] = ln.po_line

    if per_line_received:
        already_received = (
            GoodsReceiptLine.objects.filter(
                po_line_id__in=per_line_received.keys(),
                grn__status=GoodsReceipt.Status.POSTED,
            )
            .values("po_line_id")
            .annotate(total=Decimal("0") + Sum("qty_packs_received"))
        )
        already_map = {row["po_line_id"]: Decimal(row["total"] or 0) for row in already_received}
        for po_line_id, new_qty in per_line_received.items():
            po_line = po_line_map[po_line_id]
            ordered_qty = Decimal(po_line.qty_packs_ordered or 0)
            prev = already_map.get(po_line_id, Decimal("0"))
            remaining = ordered_qty - prev
            if remaining < Decimal("0"):
                remaining = Decimal("0")
            if new_qty > remaining:
                raise ValueError(
                    "Receiving quantity exceeds total ordered for PO line "
                    f"{po_line_id}. Ordered {ordered_qty}, already received {prev}, "
                    f"remaining {remaining}."
                )

    for ln in lines:
        qty_packs = Decimal(str(ln.qty_packs_received or 0))
        product: Product | None = ln.product
        if not product:
            product = _create_or_update_product_from_payload(
                ln.new_product_payload or {}, default_vendor_id=grn.po.vendor_id
            )
            ln.product = product
            ln.save(update_fields=["product"])
            if ln.po_line and not ln.po_line.product_id:
                pol = ln.po_line
                pol.product = product
                updates = ["product"]
                if not pol.requested_name:
                    pol.requested_name = product.name
                    updates.append("requested_name")
                if product.medicine_form_id and not pol.medicine_form_id:
                    pol.medicine_form_id = product.medicine_form_id
                    updates.append("medicine_form")
                pol.save(update_fields=updates)

        batch, created = BatchLot.objects.get_or_create(
            product=product,
            batch_no=ln.batch_no,
            defaults={
                "mfg_date": ln.mfg_date,
                "expiry_date": ln.expiry_date,
                "status": BatchLot.Status.ACTIVE,
            },
        )
        # Update lot info if missing
        batch_updates: list[str] = []
        if ln.mfg_date and not batch.mfg_date:
            batch.mfg_date = ln.mfg_date
            batch_updates.append("mfg_date")
        if ln.expiry_date and not batch.expiry_date:
            batch.expiry_date = ln.expiry_date
            batch_updates.append("expiry_date")
        # Suggest/assign rack
        rack = ln.rack_no or assign_rack(grn.location_id, product.manufacturer or "")
        if rack and batch.rack_no != rack:
            batch.rack_no = rack
            batch_updates.append("rack_no")

        if ln.unit_cost is not None:
            price_pack = Decimal(str(ln.unit_cost))
            if batch.purchase_price != price_pack:
                batch.purchase_price = price_pack
                batch_updates.append("purchase_price")
            units_per_pack = product.units_per_pack or Decimal("1")
            if units_per_pack > 0:
                per_base = (price_pack / units_per_pack).quantize(
                    PRICE_PER_BASE_QUANT, rounding=ROUND_HALF_UP
                )
                if batch.purchase_price_per_base != per_base:
                    batch.purchase_price_per_base = per_base
                    batch_updates.append("purchase_price_per_base")

        needs_initial_update = created or not (batch.initial_quantity or Decimal("0"))

        qty_base = ln.qty_base_received
        if qty_base in (None, 0):
            try:
                qty_base, _ = convert_quantity_to_base(
                    quantity=Decimal(str(ln.qty_packs_received or 0)),
                    base_uom=product.base_uom,
                    selling_uom=product.selling_uom,
                    quantity_uom=product.selling_uom,
                    units_per_pack=product.units_per_pack or Decimal("1"),
                    tablets_per_strip=getattr(product, "tablets_per_strip", None),
                    strips_per_box=getattr(product, "strips_per_box", None),
                )
            except Exception:
                qty_base = packs_to_base(product.id, Decimal(ln.qty_packs_received))
        ln.qty_base_received = qty_base
        ln.save(update_fields=["qty_base_received"])

        if needs_initial_update and qty_base:
            batch.initial_quantity = qty_packs
            batch.initial_quantity_base = qty_base
            batch_updates.extend(["initial_quantity", "initial_quantity_base"])

        if batch_updates:
            batch.save(update_fields=sorted(set(batch_updates)))

        product_updates: list[str] = []
        if ln.mrp is not None:
            mrp = Decimal(str(ln.mrp))
            if product.mrp != mrp:
                product.mrp = mrp
                product_updates.append("mrp")
        if product_updates:
            product.save(update_fields=product_updates)
        write_movement(
            location_id=grn.location_id,
            batch_lot_id=batch.id,
            qty_change_base=qty_base - (ln.qty_base_damaged or Decimal("0")),
            reason="PURCHASE",
            ref_doc=("GRN", grn.id),
            actor=actor,
        )

    # Update PO line received qty and status
    po = grn.po
    # aggregate received per po_line
    recvd = (
        GoodsReceiptLine.objects.filter(po_line__po=po)
        .values("po_line_id")
        .annotate(total=Decimal("0") + Sum("qty_packs_received"))
    )
    recvd_map = {r["po_line_id"]: r["total"] for r in recvd}
    all_received = True
    any_received = False
    for pol in po.lines.all():
        got = recvd_map.get(pol.id, 0) or 0
        any_received = any_received or (got > 0)
        if got < (pol.qty_packs_ordered or 0):
            all_received = False
    po.status = (
        PurchaseOrder.Status.COMPLETED if all_received else (
            PurchaseOrder.Status.PARTIALLY_RECEIVED if any_received else PurchaseOrder.Status.OPEN
        )
    )
    po.save(update_fields=["status"])

    grn.received_at = timezone.now()
    grn.received_by_id = getattr(actor, "id", None)
    grn.status = GoodsReceipt.Status.POSTED
    grn.save(update_fields=["status", "received_at", "received_by"])

    audit(
        actor,
        table="procurement_goodsreceipt",
        row_id=grn.id,
        action="POSTED",
        before=None,
        after={"status": grn.status, "po_id": grn.po_id},
    )
    emit_event("GRN_POSTED", {"grn_id": grn.id, "po_id": grn.po_id})


def _create_or_update_product_from_payload(payload: dict, default_vendor_id=None) -> Product:
    if not payload:
        raise ValueError("Product details are required for new medicines.")
    from decimal import Decimal as _Decimal

    name = payload.get("name")
    product = None
    product_id = payload.get("product_id") or payload.get("id")
    if product_id:
        product = Product.objects.filter(id=product_id).first()
    if not product:
        code = payload.get("code")
        if code:
            product = Product.objects.filter(code__iexact=code).first()
    if not product and name:
        product = Product.objects.filter(name__iexact=name).first()

    # Handle category - can be ID (int), name (str), or None
    category_value = payload.get("category") or payload.get("category_id")
    category_id = None
    if category_value is not None:
        try:
            # Try to treat as integer ID
            category_id = int(category_value)
            # Verify it exists
            if not ProductCategory.objects.filter(id=category_id).exists():
                category_id = None
        except (ValueError, TypeError):
            # Not a number - treat as category name
            # Map frontend category string IDs to database category names
            CATEGORY_MAPPING = {
                'tablet': 'Tablet',
                'capsule': 'Capsule',
                'syrup': 'Syrup/Suspension',
                'injection': 'Injection/Vial',
                'ointment': 'Ointment/Cream',
                'drops': 'Drops (Eye/Ear/Nasal)',
                'inhaler': 'Inhaler',
                'powder': 'Powder/Sachet',
                'gel': 'Gel',
                'spray': 'Spray',
                'lotion': 'Lotion/Solution',
                'shampoo': 'Shampoo',
                'soap': 'Soap/Bar',
                'bandage': 'Bandage/Dressing',
                'mask': 'Mask (Surgical/N95)',
                'gloves': 'Gloves',
                'cotton': 'Cotton/Gauze',
                'sanitizer': 'Hand Sanitizer',
                'thermometer': 'Thermometer',
                'supplement': 'Supplement/Vitamin',
                'other': 'Other/Miscellaneous',
            }
            category_name = None
            if isinstance(category_value, str) and category_value.lower() in CATEGORY_MAPPING:
                category_name = CATEGORY_MAPPING[category_value.lower()]
            else:
                category_name = str(category_value)
            
            # Find or create the category
            category_obj, created = ProductCategory.objects.get_or_create(
                name=category_name,
                defaults={'is_active': True}
            )
            category_id = category_obj.id

    fields = {
        "name": name,
        "generic_name": payload.get("generic_name"),
        "dosage_strength": payload.get("dosage_strength"),
        "hsn": payload.get("hsn"),
        "schedule": payload.get("schedule") or Product.Schedule.OTC,
        "category_id": category_id,
        "medicine_form_id": payload.get("medicine_form"),
        "pack_size": payload.get("pack_size"),
        "manufacturer": payload.get("manufacturer"),
        "mrp": _Decimal(str(payload.get("mrp"))) if payload.get("mrp") is not None else None,
        "base_unit": payload.get("base_unit"),
        "pack_unit": payload.get("pack_unit"),
        "units_per_pack": _Decimal(str(payload.get("units_per_pack")))
        if payload.get("units_per_pack") is not None
        else None,
        "base_unit_step": _Decimal(str(payload.get("base_unit_step")))
        if payload.get("base_unit_step") is not None
        else None,
        "gst_percent": _Decimal(str(payload.get("gst_percent")))
        if payload.get("gst_percent") is not None
        else None,
        "reorder_level": _Decimal(str(payload.get("reorder_level")))
        if payload.get("reorder_level") is not None
        else None,
        "description": payload.get("description"),
        "storage_instructions": payload.get("storage_instructions"),
        "preferred_vendor_id": payload.get("preferred_vendor")
        or payload.get("preferred_vendor_id")
        or default_vendor_id,
        "is_sensitive": payload.get("is_sensitive"),
    }

    if product:
        update_fields = []
        for attr, value in fields.items():
            if value is not None and getattr(product, attr) != value:
                setattr(product, attr, value)
                update_fields.append(attr)
        if update_fields:
            product.save(update_fields=update_fields)
        return product

    if not name:
        raise ValueError("Product name is required.")
    required = ["base_unit", "pack_unit", "units_per_pack", "mrp"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"Missing product fields: {', '.join(missing)}")
    code = payload.get("code")
    if not code:
        last = Product.objects.order_by("-id").first()
        next_id = (last.id + 1) if last else 1
        code = f"PRD-{next_id:05d}"
    product = Product.objects.create(
        code=code,
        name=name,
        generic_name=fields["generic_name"] or "",
        dosage_strength=fields["dosage_strength"] or "",
        hsn=fields["hsn"] or "",
        schedule=fields["schedule"],
        category_id=fields["category_id"],
        medicine_form_id=fields["medicine_form_id"],
        pack_size=fields["pack_size"] or "",
        manufacturer=fields["manufacturer"] or "",
        mrp=fields["mrp"],
        base_unit=fields["base_unit"],
        pack_unit=fields["pack_unit"],
        units_per_pack=fields["units_per_pack"],
        base_unit_step=fields["base_unit_step"] or _Decimal("1.000"),
        gst_percent=fields["gst_percent"] or _Decimal("0"),
        reorder_level=fields["reorder_level"] or _Decimal("0"),
        description=fields["description"] or "",
        storage_instructions=fields["storage_instructions"] or "",
        preferred_vendor_id=fields["preferred_vendor_id"],
        is_sensitive=bool(fields["is_sensitive"]),
        is_active=True,
    )
    return product


@transaction.atomic
def post_vendor_return(vendor_return_id: int, actor) -> None:
    vr = (
        VendorReturn.objects.select_for_update()
        .select_related("purchase_line", "batch_lot", "purchase_line__purchase")
        .get(id=vendor_return_id)
    )
    purchase = vr.purchase_line.purchase

    # Ensure stock availability
    from apps.inventory.services import stock_on_hand

    soh = stock_on_hand(location_id=purchase.location_id, batch_lot_id=vr.batch_lot_id)
    if soh < vr.qty_base:
        raise ValueError("Insufficient stock to return to vendor")

    write_movement(
        location_id=purchase.location_id,
        batch_lot_id=vr.batch_lot_id,
        qty_change_base=-vr.qty_base,
        reason="RETURN_VENDOR",
        ref_doc=("VENDOR_RETURN", vr.id),
        actor=actor,
    )
    vr.status = "CREDITED"
    vr.save(update_fields=["status"])

    audit(
        actor,
        table="procurement_vendorreturn",
        row_id=vr.id,
        action="POSTED",
        before=None,
        after={"status": vr.status},
    )

