from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import SalesInvoice, SalesLine
from apps.catalog.models import BatchLot
from apps.inventory.models import InventoryLedger
from apps.compliance.models import H1RegisterEntry  # for compliance hook

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")

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
        ref_doc_id=ref_doc_id,
    )

def audit_log(actor, table, obj_id, action):
    # optional: wire to apps.audit if present
    try:
        from apps.audit.models import AuditLog
        AuditLog.objects.create(actor_user_id=actor.id if actor else None, action=action, table_name=table, record_id=obj_id)
    except Exception:
        pass

@transaction.atomic
def post_invoice(invoice_id, actor):
    inv = SalesInvoice.objects.select_for_update().prefetch_related("lines__batch_lot", "lines__product").get(pk=invoice_id)
    if inv.status == SalesInvoice.Status.POSTED:
        raise ValidationError("Invoice already posted")

    gross = Decimal("0")
    tax_total = Decimal("0")
    discount_total = Decimal("0")
    net = Decimal("0")

    # Validate lines first
    for line in inv.lines.all():
        batch = line.batch_lot
        if batch.status != BatchLot.Status.ACTIVE:
            raise ValidationError(f"Batch {batch.batch_no} not sellable")
        if batch.expiry_date and batch.expiry_date < timezone.now().date():
            raise ValidationError(f"Batch {batch.batch_no} expired")
        available = stock_on_hand(inv.location_id, batch.id)
        if available < line.qty_base:
            raise ValidationError(f"Insufficient stock for batch {batch.batch_no}: available {available}, required {line.qty_base}")

        qty = Decimal(line.qty_base)
        rate = Decimal(line.rate_per_base)
        disc = Decimal(line.discount_amount or 0)
        taxable = (qty * rate) - disc
        tax_amt = Decimal(line.tax_amount or (taxable * Decimal(line.tax_percent or 0) / Decimal("100")))
        tax_amt = tax_amt.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
        line_total = (taxable + tax_amt).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        SalesLine.objects.filter(pk=line.pk).update(tax_amount=tax_amt, line_total=line_total)

        gross += (qty * rate)
        discount_total += disc
        tax_total += tax_amt
        net += line_total

    # write movements
    for line in inv.lines.all():
        write_movement(inv.location_id, line.batch_lot_id, -line.qty_base, "SALE", "SalesInvoice", inv.id)

        # create H1 entry if needed (simplified)
        if line.requires_prescription:
            H1RegisterEntry.objects.create(
                invoice=inv,
                line=line,
                product=line.product,
                batch_lot=line.batch_lot,
                drug_name_snapshot=line.product_name or line.product.name,
                batch_no_snapshot=line.batch_no,
                expiry_snapshot=line.expiry_date,
                patient_name=inv.patient_name or "",
                patient_address=inv.customer.billing_address or "",
                doctor_name=inv.doctor_name or "",
                doctor_reg_no=inv.doctor_reg_no or "",
                qty_issued_base=line.qty_base,
                balance_after_issue_base=stock_on_hand(inv.location_id, line.batch_lot_id) - line.qty_base,
                entry_date=timezone.now()
            )

    inv.gross_total = gross.quantize(CURRENCY_QUANT)
    inv.discount_total = discount_total.quantize(CURRENCY_QUANT)
    inv.tax_total = tax_total.quantize(CURRENCY_QUANT)
    inv.net_total = net.quantize(CURRENCY_QUANT)
    inv.status = SalesInvoice.Status.POSTED
    inv.posted_at = timezone.now()
    inv.posted_by = actor
    inv.save()

    # recompute payment status
    payments_total = sum([p.amount for p in inv.payments.all()]) if hasattr(inv, "payments") else Decimal("0")
    if payments_total >= inv.net_total:
        inv.payment_status = SalesInvoice.PaymentStatus.PAID
    elif payments_total > 0:
        inv.payment_status = SalesInvoice.PaymentStatus.PARTIAL
    else:
        inv.payment_status = SalesInvoice.PaymentStatus.CREDIT
    inv.save(update_fields=["payment_status"])

    audit_log(actor, "sales_invoices", inv.id, "POST")
    return {"invoice_id": inv.id, "invoice_no": inv.invoice_no, "status": "POSTED"}
