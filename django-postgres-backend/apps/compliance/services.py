from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from .models import Prescription, H1RegisterEntry, NDPSDailyEntry


def ensure_prescription_for_invoice(invoice):
    """Validates that a prescription exists for H1/NDPS lines."""
    requires_rx = any(l.product.schedule in {"H1", "NDPS"} for l in invoice.lines.all())
    if requires_rx and not hasattr(invoice, "prescription"):
        raise ValidationError(f"Prescription required for invoice {invoice.invoice_no} (H1/NDPS items present).")
    return True


@transaction.atomic
def create_compliance_entries(invoice):
    """Creates H1 and NDPS entries for posted invoice lines."""
    prescription = getattr(invoice, "prescription", None)
    for line in invoice.lines.all():
        schedule = getattr(line.product, "schedule", None)
        if schedule == "H1":
            H1RegisterEntry.objects.create(
                sale_line=line,
                patient_name=prescription.patient_name if prescription else "",
                prescriber_name=prescription.prescriber_name if prescription else "",
                prescriber_reg_no=prescription.prescriber_reg_no if prescription else "",
                entry_date=invoice.invoice_date.date(),
            )
        elif schedule == "NDPS":
            _upsert_ndps_entry(line.product, invoice.invoice_date.date(), line.qty_base)


def _upsert_ndps_entry(product, entry_date, qty_issued):
    """Upserts NDPSDailyEntry for a specific product/date."""
    entry, created = NDPSDailyEntry.objects.get_or_create(
        product=product,
        entry_date=entry_date,
        defaults=dict(opening_balance=0, qty_issued=0, closing_balance=0),
    )
    entry.qty_issued += Decimal(qty_issued)
    entry.closing_balance = entry.opening_balance - entry.qty_issued
    entry.save()


def recompute_ndps_daily(product_id, start_date, end_date):
    """Recomputes NDPS daily balances between dates."""
    entries = NDPSDailyEntry.objects.filter(product_id=product_id, entry_date__range=[start_date, end_date]).order_by("entry_date")
    prev_balance = Decimal("0")
    for e in entries:
        e.opening_balance = prev_balance
        e.closing_balance = e.opening_balance - e.qty_issued
        e.save()
        prev_balance = e.closing_balance
