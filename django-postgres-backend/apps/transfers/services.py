from django.db import transaction
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import TransferVoucher
from apps.inventory.models import InventoryLedger

def stock_on_hand(location_id, batch_lot_id):
    from django.db.models import Sum
    s = InventoryLedger.objects.filter(location_id=location_id, batch_lot_id=batch_lot_id).aggregate(total=Sum("qty_change_base"))
    return Decimal(s["total"] or 0)

def write_movement(location_id, batch_lot_id, qty_delta, reason, ref_doc_type, ref_doc_id):
    InventoryLedger.objects.create(
        location_id=location_id,
        batch_lot_id=batch_lot_id,
        qty_change_base=qty_delta,
        reason=reason,
        ref_doc_type=ref_doc_type,
        ref_doc_id=ref_doc_id
    )

@transaction.atomic
def post_transfer(voucher_id, actor):
    v = TransferVoucher.objects.select_for_update().prefetch_related("lines__batch_lot").get(pk=voucher_id)
    if v.from_location_id == v.to_location_id:
        raise ValidationError("from and to cannot be same")
    if v.status == TransferVoucher.Status.CANCELLED:
        raise ValidationError("voucher cancelled")

    # stock checks
    for l in v.lines.all():
        if stock_on_hand(v.from_location_id, l.batch_lot_id) < l.qty_base:
            raise ValidationError(f"Insufficient stock for batch {l.batch_lot.batch_no}")

    # write out and in
    for l in v.lines.all():
        write_movement(v.from_location_id, l.batch_lot_id, -l.qty_base, "TRANSFER_OUT", "TransferVoucher", v.id)
        write_movement(v.to_location_id, l.batch_lot_id, +l.qty_base, "TRANSFER_IN", "TransferVoucher", v.id)

    v.status = TransferVoucher.Status.IN_TRANSIT
    v.posted_at = timezone.now()
    v.posted_by = actor
    v.save()
    # audit log optional
    return {"voucher_id": v.id, "status": v.status}

@transaction.atomic
def receive_transfer(voucher_id, actor):
    v = TransferVoucher.objects.select_for_update().get(pk=voucher_id)
    if v.status != TransferVoucher.Status.IN_TRANSIT:
        raise ValidationError("Voucher not in IN_TRANSIT")
    v.status = TransferVoucher.Status.RECEIVED
    v.save(update_fields=["status"])
    return {"voucher_id": v.id, "status": v.status}
