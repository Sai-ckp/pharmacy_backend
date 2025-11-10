from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import SalesInvoice, SalesLine
from apps.inventory.models import InventoryMovement
from apps.compliance.services import (
    ensure_prescription_for_invoice,
    create_compliance_entries,
)
from apps.governance.models import AuditLog

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")


def stock_on_hand(location_id, batch_lot_id):
    """Aggregate available stock from InventoryMovement."""
    from django.db.models import Sum
    s = (
        InventoryMovement.objects.filter(
            location_id=location_id, batch_lot_id=batch_lot_id
        ).aggregate(total=Sum("qty_change_base"))
    )
    return Decimal(s["total"] or 0)


def write_movement(location_id, batch_lot_id, qty_delta, reason, ref_doc_type, ref_doc_id):
    """Write inventory movement for sales transaction."""
    InventoryMovement.objects.create(
        location_id=location_id,
        batch_lot_id=batch_lot_id,
        qty_change_base=qty_delta,
        reason=reason,
        ref_doc_type=ref_doc_type,
        ref_doc_id=ref_doc_id,
    )


@transaction.atomic
def post_invoice(actor, invoice_id):
    """Post a draft invoice into a confirmed sale."""
    inv = (
        SalesInvoice.objects.select_for_update()
        .prefetch_related("lines__batch_lot", "lines__product")
        .get(pk=invoice_id)
    )

    if inv.status != SalesInvoice.Status.DRAFT:
        raise ValidationError(f"Cannot post invoice in {inv.status} state.")

    # ✅ Compliance: Check if prescription required
    ensure_prescription_for_invoice(inv)

    gross = Decimal("0")
    tax_total = Decimal("0")
    discount_total = Decimal("0")
    net = Decimal("0")

    # ✅ Validate & compute totals
    for line in inv.lines.all():
        available = stock_on_hand(inv.location_id, line.batch_lot_id)
        if available < line.qty_base:
            raise ValidationError(
                f"Insufficient stock for batch {line.batch_lot.batch_no}: "
                f"available {available}, required {line.qty_base}"
            )

        qty = Decimal(line.qty_base)
        rate = Decimal(line.rate_per_base)
        disc = Decimal(line.discount_amount or 0)
        taxable = (qty * rate) - disc
        tax_amt = (
            taxable * Decimal(line.tax_percent or 0) / Decimal("100")
        ).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        line_total = (taxable + tax_amt).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        # update computed fields
        SalesLine.objects.filter(pk=line.pk).update(
            tax_amount=tax_amt, line_total=line_total
        )

        gross += qty * rate
        discount_total += disc
        tax_total += tax_amt
        net += line_total

        # record stock deduction
        write_movement(
            inv.location_id,
            line.batch_lot_id,
            -qty,
            "SALE",
            "SalesInvoice",
            inv.id,
        )

    # ✅ Finalize invoice totals
    inv.gross_total = gross.quantize(CURRENCY_QUANT)
    inv.discount_total = discount_total.quantize(CURRENCY_QUANT)
    inv.tax_total = tax_total.quantize(CURRENCY_QUANT)
    inv.net_total = net.quantize(CURRENCY_QUANT)
    inv.status = SalesInvoice.Status.POSTED
    inv.posted_at = timezone.now()
    inv.posted_by = actor
    inv.save()

    # ✅ Compliance hooks (create H1 / NDPS entries)
    create_compliance_entries(inv)

    # ✅ Update payment status
    _update_payment_status(inv)

    # ✅ Audit log
    _audit(actor, "sales_invoices", inv.id, "POST")

    return {"invoice_no": inv.invoice_no, "status": inv.status}


@transaction.atomic
def cancel_invoice(actor, invoice_id):
    """Reverse a posted invoice."""
    inv = SalesInvoice.objects.select_for_update().get(pk=invoice_id)
    if inv.status != SalesInvoice.Status.POSTED:
        raise ValidationError("Only POSTED invoices can be cancelled.")

    # Reverse stock (credit back)
    for line in inv.lines.all():
        write_movement(
            inv.location_id,
            line.batch_lot_id,
            line.qty_base,
            "ADJUSTMENT",
            "SalesInvoiceCancel",
            inv.id,
        )

    inv.status = SalesInvoice.Status.CANCELLED
    inv.save()

    _audit(actor, "sales_invoices", inv.id, "CANCEL")

    return {"invoice_no": inv.invoice_no, "status": inv.status}


def _update_payment_status(inv):
    """Recalculate invoice payment status after posting."""
    payments_total = sum(p.amount for p in inv.payments.all())

    if payments_total >= inv.net_total:
        inv.payment_status = SalesInvoice.PaymentStatus.PAID
    elif payments_total > 0:
        inv.payment_status = SalesInvoice.PaymentStatus.PARTIAL
    else:
        inv.payment_status = SalesInvoice.PaymentStatus.CREDIT

    inv.save(update_fields=["payment_status"])


def _audit(actor, table, obj_id, action):
    """Generic audit trail creation."""
    AuditLog.objects.create(
        actor_user_id=getattr(actor, "id", None),
        action=action,
        table_name=table,
        record_id=obj_id,
        created_at=timezone.now(),
    )
