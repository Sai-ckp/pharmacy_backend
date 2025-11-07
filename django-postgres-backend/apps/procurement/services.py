from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import BatchLot, Product
from apps.inventory.services import write_movement
from .models import Purchase, PurchaseLine, VendorReturn
from apps.governance.models import AuditLog


@transaction.atomic
def post_purchase(purchase_id, actor=None):
    p = Purchase.objects.select_for_update().get(id=purchase_id)
    total = Decimal("0")
    for line in p.lines.select_related("product"):
        product: Product = line.product
        # Compute received_base_qty
        received = Decimal(line.qty_packs) * (product.units_per_pack or Decimal("0"))
        line.received_base_qty = received
        line.save(update_fields=["received_base_qty"])

        batch, _ = BatchLot.objects.get_or_create(
            product=product, batch_no=line.batch_no,
            defaults={"expiry_date": line.expiry_date, "status": BatchLot.Status.ACTIVE}
        )
        write_movement(
            location_id=p.location_id,
            batch_lot_id=batch.id,
            qty_change_base=received,
            reason="PURCHASE",
            ref_doc_type="PURCHASE",
            ref_doc_id=str(p.id),
        )
        total += (line.unit_cost * Decimal(line.qty_packs))

    p.gross_total = total
    p.net_total = total  # simple for now
    p.save(update_fields=["gross_total", "net_total"])

    AuditLog.objects.create(
        actor_user=actor, action="POST_PURCHASE", table_name="procurement_purchase",
        record_id=str(p.id), before_json=None, after_json={"gross_total": str(p.gross_total)}
    )
    return p


@transaction.atomic
def post_vendor_return(vendor_return_id, actor=None):
    vr = VendorReturn.objects.select_for_update().select_related("purchase_line", "batch_lot", "purchase_line__purchase").get(id=vendor_return_id)
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
        ref_doc_type="VENDOR_RETURN",
        ref_doc_id=str(vr.id),
    )
    vr.status = "POSTED"
    vr.save(update_fields=["status"])

    AuditLog.objects.create(
        actor_user=actor, action="POST_VENDOR_RETURN", table_name="procurement_vendorreturn",
        record_id=str(vr.id), before_json=None, after_json={"status": vr.status}
    )
    return vr

