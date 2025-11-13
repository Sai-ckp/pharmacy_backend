from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import BatchLot, Product
from apps.catalog.services import packs_to_base
from apps.inventory.services import write_movement
from apps.inventory.models import RackRule
from .models import (
    Purchase, PurchaseLine, VendorReturn, GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine,
)
from apps.governance.services import audit, emit_event


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

    for ln in grn.lines.all():
        if not ln.expiry_date or (ln.qty_packs_received or 0) <= 0:
            raise ValueError("Each GRN line must have expiry_date and qty_packs_received > 0")

        product: Product = ln.product
        batch, _ = BatchLot.objects.get_or_create(
            product=product,
            batch_no=ln.batch_no,
            defaults={
                "mfg_date": ln.mfg_date,
                "expiry_date": ln.expiry_date,
                "status": BatchLot.Status.ACTIVE,
            },
        )
        # Update lot info if missing
        changed = False
        if ln.mfg_date and not batch.mfg_date:
            batch.mfg_date = ln.mfg_date
            changed = True
        if ln.expiry_date and not batch.expiry_date:
            batch.expiry_date = ln.expiry_date
            changed = True
        # Suggest/assign rack
        rack = assign_rack(grn.location_id, product.manufacturer or "")
        if rack and not batch.rack_no:
            batch.rack_no = rack
            changed = True
        if changed:
            batch.save()

        qty_base = packs_to_base(product.id, Decimal(ln.qty_packs_received))
        ln.qty_base_received = qty_base
        ln.save(update_fields=["qty_base_received"])
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

    grn.status = GoodsReceipt.Status.POSTED
    grn.save(update_fields=["status"])

    audit(
        actor,
        table="procurement_goodsreceipt",
        row_id=grn.id,
        action="POSTED",
        before=None,
        after={"status": grn.status, "po_id": grn.po_id},
    )
    emit_event("GRN_POSTED", {"grn_id": grn.id, "po_id": grn.po_id})


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

