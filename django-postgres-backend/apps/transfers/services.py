from django.db import transaction
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import TransferVoucher
from apps.inventory.models import InventoryMovement

def stock_on_hand(location_id, batch_lot_id):
    from django.db.models import Sum
    s = InventoryMovement.objects.filter(
        location_id=location_id, batch_lot_id=batch_lot_id
    ).aggregate(total=Sum("qty_change_base"))
    return Decimal(s["total"] or 0)

def write_movement(location_id, batch_lot_id, qty_delta, reason, ref_doc_type, ref_doc_id):
    InventoryMovement.objects.create(
        location_id=location_id,
        batch_lot_id=batch_lot_id,
        qty_change_base=qty_delta,
        reason=reason,
        ref_doc_type=ref_doc_type,
        ref_doc_id=ref_doc_id,
    )

@transaction.atomic
def post_transfer(actor, voucher_id):
    """POST (OUT only) — marks IN_TRANSIT and writes TRANSFER_OUT."""
    v = TransferVoucher.objects.select_for_update().prefetch_related("lines__batch_lot").get(pk=voucher_id)

    if v.status != TransferVoucher.Status.DRAFT:
        raise ValidationError(f"Cannot post transfer in status {v.status}")

    for l in v.lines.all():
        available = stock_on_hand(v.from_location_id, l.batch_lot_id)
        if available < l.qty_base:
            raise ValidationError(f"Insufficient stock for batch {l.batch_lot.batch_no}")

        # Write OUT
        write_movement(v.from_location_id, l.batch_lot_id, -l.qty_base, "TRANSFER_OUT", "TransferVoucher", v.id)

    v.status = TransferVoucher.Status.IN_TRANSIT
    v.posted_at = timezone.now()
    v.posted_by = actor
    v.save()
    _audit(actor, "transfer_vouchers", v.id, "POST_OUT")
    return {"voucher_id": v.id, "status": v.status}

@transaction.atomic
def receive_transfer(actor, voucher_id):
    """Receive step — adds TRANSFER_IN, marks RECEIVED."""
    v = TransferVoucher.objects.select_for_update().prefetch_related("lines").get(pk=voucher_id)

    if v.status != TransferVoucher.Status.IN_TRANSIT:
        raise ValidationError(f"Cannot receive voucher in status {v.status}")

    for l in v.lines.all():
        # Check idempotency — if already received, skip
        existing = InventoryMovement.objects.filter(
            ref_doc_type="TransferVoucher",
            ref_doc_id=v.id,
            reason="TRANSFER_IN",
            batch_lot_id=l.batch_lot_id,
        ).exists()
        if not existing:
            write_movement(v.to_location_id, l.batch_lot_id, l.qty_base, "TRANSFER_IN", "TransferVoucher", v.id)

    v.status = TransferVoucher.Status.RECEIVED
    v.save(update_fields=["status"])
    _audit(actor, "transfer_vouchers", v.id, "RECEIVE")
    return {"voucher_id": v.id, "status": v.status}

@transaction.atomic
def cancel_transfer(actor, voucher_id):
    """Cancel transfer — allowed in DRAFT or IN_TRANSIT."""
    v = TransferVoucher.objects.select_for_update().prefetch_related("lines").get(pk=voucher_id)
    if v.status not in [TransferVoucher.Status.DRAFT, TransferVoucher.Status.IN_TRANSIT]:
        raise ValidationError(f"Cannot cancel transfer in {v.status} state")

    # If IN_TRANSIT, revert OUT movements
    if v.status == TransferVoucher.Status.IN_TRANSIT:
        for l in v.lines.all():
            write_movement(v.from_location_id, l.batch_lot_id, l.qty_base, "ADJUSTMENT", "TransferVoucherCancel", v.id)

    v.status = TransferVoucher.Status.CANCELLED
    v.save(update_fields=["status"])
    _audit(actor, "transfer_vouchers", v.id, "CANCEL")
    return {"voucher_id": v.id, "status": v.status}

def _audit(actor, table, obj_id, action):
    """Optional audit hook (governance.audit)."""
    try:
        from apps.governance.models import AuditLog
        AuditLog.objects.create(
            actor_user_id=getattr(actor, "id", None),
            action=action,
            table_name=table,
            record_id=obj_id,
            created_at=timezone.now(),
        )
    except Exception:
        pass
