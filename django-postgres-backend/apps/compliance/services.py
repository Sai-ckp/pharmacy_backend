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
    prescription = getattr(invoice, "prescription", None)

    for line in invoice.lines.all():
        schedule = getattr(line.product, "schedule", None)

        # H1 register
        if schedule == "H1":
            H1RegisterEntry.objects.create(
                invoice=invoice,
                line=line,
                product=line.product,
                batch_lot=line.batch_lot,
                drug_name_snapshot=line.product.name,
                batch_no_snapshot=line.batch_lot.batch_no,
                expiry_snapshot=line.batch_lot.expiry,

                patient_name=getattr(prescription, "customer", None).name if prescription else None,
                patient_address=getattr(prescription, "customer", None).address if prescription else None,

                doctor_name=getattr(prescription, "doctor_name", None),
                doctor_reg_no=getattr(prescription, "doctor_reg_no", None),

                qty_issued_base=line.qty_base,
                entry_date=invoice.invoice_date,
            )

        # NDPS register
        elif schedule == "NDPS":
            _upsert_ndps_entry(
                product=line.product,
                entry_date=invoice.invoice_date.date(),
                qty_issued=line.qty_base,
            )



def _upsert_ndps_entry(product, entry_date, qty_issued):
    entry, created = NDPSDailyEntry.objects.get_or_create(
        date=entry_date,
        product=product,
        defaults=dict(
            opening_qty_base=Decimal("0"),
            in_qty_base=Decimal("0"),
            out_qty_base=Decimal("0"),
            closing_qty_base=Decimal("0"),
        )
    )

    # OUT entry
    entry.out_qty_base += Decimal(qty_issued)

    # Closing = opening + IN - OUT
    entry.closing_qty_base = (
        entry.opening_qty_base + entry.in_qty_base - entry.out_qty_base
    )

    entry.save()



def recompute_ndps_daily(product_id, start_date, end_date):
    entries = NDPSDailyEntry.objects.filter(
        product_id=product_id,
        date__range=[start_date, end_date]
    ).order_by("date")

    prev_closing = Decimal("0")

    for e in entries:
        e.opening_qty_base = prev_closing
        e.closing_qty_base = (
            e.opening_qty_base + e.in_qty_base - e.out_qty_base
        )
        e.save()
        prev_closing = e.closing_qty_base

