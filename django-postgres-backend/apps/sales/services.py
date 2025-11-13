# apps/sales/services.py
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
    from django.db.models import Sum

    s = (
        InventoryMovement.objects.filter(
            location_id=location_id, batch_lot_id=batch_lot_id
        ).aggregate(total=Sum("qty_change_base"))
    )
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
def post_invoice(actor, invoice_id):
    """Post a draft invoice into a confirmed sale. Idempotent: re-posting a POSTED invoice returns no-op."""
    inv = (
        SalesInvoice.objects.select_for_update()
        .prefetch_related("lines__batch_lot", "lines__product", "payments")
        .get(pk=invoice_id)
    )

    # Idempotency: already posted → no-op
    if inv.status == SalesInvoice.Status.POSTED:
        return {"invoice_no": inv.invoice_no, "status": inv.status}

    if inv.status != SalesInvoice.Status.DRAFT:
        raise ValidationError(f"Cannot post invoice in {inv.status} state.")

    # Compliance: ensure prescription exists if required
    ensure_prescription_for_invoice(inv)

    gross = Decimal("0")
    tax_total = Decimal("0")
    discount_total = Decimal("0")
    net = Decimal("0")

    # -----------------------------------------
    # INVENTORY DEDUCTION + TOTAL COMPUTATION
    # -----------------------------------------
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
        tax_amt = (taxable * Decimal(line.tax_percent or 0) / Decimal("100")).quantize(
            AMOUNT_QUANT, rounding=ROUND_HALF_UP
        )
        line_total = (taxable + tax_amt).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

        # update calculated values on DB
        SalesLine.objects.filter(pk=line.pk).update(tax_amount=tax_amt, line_total=line_total)

        gross += qty * rate
        discount_total += disc
        tax_total += tax_amt
        net += line_total

        # Stock OUT movement
        write_movement(inv.location_id, line.batch_lot_id, -qty, "SALE", "SalesInvoice", inv.id)

    # -----------------------------------------
    # FINAL TOTALS
    # -----------------------------------------
    net_rounded = net.quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)
    round_off = (net_rounded - net).quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)

    inv.gross_total = gross.quantize(CURRENCY_QUANT)
    inv.discount_total = discount_total.quantize(CURRENCY_QUANT)
    inv.tax_total = tax_total.quantize(CURRENCY_QUANT)
    inv.round_off_amount = round_off
    inv.net_total = net_rounded

    inv.status = SalesInvoice.Status.POSTED
    inv.posted_at = timezone.now()
    inv.posted_by = actor
    inv.save()

    # -----------------------------------------
    # COMPLIANCE (H1 / NDPS)
    # -----------------------------------------
    create_compliance_entries(inv)

    # -----------------------------------------
    # PAYMENT STATUS UPDATE
    # -----------------------------------------
    _update_payment_status(inv)

    # -----------------------------------------
    # NOTIFICATION CHECKS (Low Stock + Expiry)
    # -----------------------------------------
    # Import notifications and settings defensively so tests/environments without those modules don't fail.
    try:
        from apps.notifications.services import enqueue_once
    except Exception:
        enqueue_once = None

    try:
        from apps.settingsx.services import get_setting
    except Exception:
        get_setting = lambda *args, **kwargs: 30

    expiry_window_days = int(get_setting("CRITICAL_EXPIRY_DAYS", 30))

    for line in inv.lines.all():
        batch = line.batch_lot
        product = line.product

        # If notifications unavailable skip
        if enqueue_once is None:
            continue

        # LOW STOCK CHECK
        available = stock_on_hand(inv.location_id, batch.id)
        if available <= product.reorder_level:
            dedupe_key = f"{inv.location_id}-{batch.id}-LOW_STOCK"
            enqueue_once(
                channel="EMAIL",
                to="alerts@erp.local",
                subject=f"Low Stock Alert: {product.name}",
                message=(
                    f"Stock for {product.name} (Batch {batch.batch_no}) at "
                    f"{inv.location.name} is low: {available}"
                ),
                dedupe_key=dedupe_key,
            )

        # EXPIRY CHECK
        # Note: product/batch fields use expiry_date on BatchLot
        if getattr(batch, "expiry_date", None):
            days_to_expiry = (batch.expiry_date - timezone.now().date()).days
            if days_to_expiry <= expiry_window_days:
                dedupe_key = f"{inv.location_id}-{batch.id}-EXPIRY"
                enqueue_once(
                    channel="EMAIL",
                    to="alerts@erp.local",
                    subject=f"Expiry Alert: {product.name}",
                    message=(f"Batch {batch.batch_no} of {product.name} expires on {batch.expiry_date}."),
                    dedupe_key=dedupe_key,
                )

    # -----------------------------------------
    # AUDIT LOGGING
    # -----------------------------------------
    _audit(actor, "sales_invoices", inv.id, "POST")

    return {"invoice_no": inv.invoice_no, "status": inv.status}


@transaction.atomic
def cancel_invoice(actor, invoice_id):
    """Reverse a posted invoice. Only POSTED invoices may be cancelled."""
    inv = SalesInvoice.objects.select_for_update().get(pk=invoice_id)
    if inv.status != SalesInvoice.Status.POSTED:
        raise ValidationError("Only POSTED invoices can be cancelled.")

    # Reverse stock (credit back)
    for line in inv.lines.all():
        write_movement(
            inv.location_id,
            line.batch_lot_id,
            Decimal(line.qty_base),
            "ADJUSTMENT",
            "SalesInvoiceCancel",
            inv.id,
        )

    inv.status = SalesInvoice.Status.CANCELLED
    inv.save(update_fields=["status"])

    _audit(actor, "sales_invoices", inv.id, "CANCEL")

    return {"invoice_no": inv.invoice_no, "status": inv.status}


def _update_payment_status(inv):
    """Recalculate invoice payment status and persist totals."""
    # refresh relations to read fresh payments
    inv.refresh_from_db(fields=[])

    payments_total = Decimal("0")
    for p in inv.payments.all():
        payments_total += Decimal(p.amount)

    inv.total_paid = payments_total.quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)
    inv.outstanding = (Decimal(inv.net_total or 0) - inv.total_paid).quantize(
        CURRENCY_QUANT, rounding=ROUND_HALF_UP
    )

    if inv.total_paid >= (inv.net_total or Decimal("0")):
        inv.payment_status = SalesInvoice.PaymentStatus.PAID
    elif inv.total_paid > Decimal("0"):
        inv.payment_status = SalesInvoice.PaymentStatus.PARTIAL
    else:
        inv.payment_status = SalesInvoice.PaymentStatus.CREDIT

    inv.save(update_fields=["payment_status", "total_paid", "outstanding"])
    return inv


def _audit(actor, table_name, record_id, action):
    """Generic audit trail creation. Avoid FK errors during tests."""
    try:
        actor_id = actor.id if actor and hasattr(actor, "id") else None
    except:
        actor_id = None

    AuditLog.objects.create(
        actor_user_id=actor_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        created_at=timezone.now(),
    )


