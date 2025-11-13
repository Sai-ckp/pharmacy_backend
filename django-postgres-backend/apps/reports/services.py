import csv, os, uuid
from django.conf import settings
from django.utils import timezone

from .models import ReportExport
from apps.sales.models import SalesInvoice
from apps.compliance.models import H1RegisterEntry, NDPSDailyEntry
from apps.inventory.models import InventoryMovement


EXPORT_DIR = os.path.join(settings.MEDIA_ROOT, "exports")


def generate_report_file(export: ReportExport):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"{uuid.uuid4()}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)

    params = export.params or {}

    with open(filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        # ------------------------------
        # SALES REGISTER
        # ------------------------------
        if export.report_type == "SALES_REGISTER":
            writer.writerow([
                "Invoice No", "Invoice Date", "Customer", "Product", "Batch",
                "Qty", "Rate", "Tax %", "Tax Amt", "Line Total", "Net Total"
            ])

            qs = SalesInvoice.objects.prefetch_related("lines__product", "lines__batch_lot")

            if params.get("date_from"):
                qs = qs.filter(invoice_date__date__gte=params["date_from"])
            if params.get("date_to"):
                qs = qs.filter(invoice_date__date__lte=params["date_to"])
            if params.get("customer"):
                qs = qs.filter(customer_id=params["customer"])
            if params.get("location"):
                qs = qs.filter(location_id=params["location"])

            for inv in qs:
                for line in inv.lines.all():
                    writer.writerow([
                        inv.invoice_no,
                        inv.invoice_date,
                        inv.customer.name if inv.customer else "",
                        line.product.name,
                        line.batch_lot.batch_no,
                        line.qty_base,
                        line.rate_per_base,
                        line.tax_percent,
                        line.tax_amount,
                        line.line_total,
                        inv.net_total,
                    ])

        # ------------------------------
        # H1 REGISTER
        # ------------------------------
        elif export.report_type == "H1_REGISTER":
            writer.writerow([
                "Invoice No", "Entry Date", "Product", "Batch", "Qty",
                "Patient", "Doctor", "Doctor Reg No"
            ])

            qs = H1RegisterEntry.objects.select_related("invoice", "product", "batch_lot")

            if params.get("date_from"):
                qs = qs.filter(entry_date__date__gte=params["date_from"])
            if params.get("date_to"):
                qs = qs.filter(entry_date__date__lte=params["date_to"])
            if params.get("invoice"):
                qs = qs.filter(invoice_id=params["invoice"])
            if params.get("product"):
                qs = qs.filter(product_id=params["product"])

            for e in qs:
                writer.writerow([
                    e.invoice.invoice_no if e.invoice else "",
                    e.entry_date,
                    e.product.name if e.product else "",
                    e.batch_lot.batch_no if e.batch_lot else "",
                    e.qty_issued_base,
                    e.patient_name,
                    e.doctor_name,
                    e.doctor_reg_no,
                ])

        # ------------------------------
        # NDPS DAILY
        # ------------------------------
        elif export.report_type == "NDPS_DAILY":
            writer.writerow(["Date", "Product", "Opening", "Issued", "Closing"])

            qs = NDPSDailyEntry.objects.select_related("product")

            if params.get("date_from"):
                qs = qs.filter(date__gte=params["date_from"])
            if params.get("date_to"):
                qs = qs.filter(date__lte=params["date_to"])
            if params.get("product"):
                qs = qs.filter(product_id=params["product"])

            for e in qs:
                writer.writerow([
                    e.date,
                    e.product.name,
                    e.opening_qty_base,
                    e.out_qty_base,
                    e.closing_qty_base,
                ])

        # ------------------------------
        # STOCK LEDGER
        # ------------------------------
        elif export.report_type == "STOCK_LEDGER":
            writer.writerow(["Movement Date", "Location", "Product", "Batch", "Reason", "Qty Change"])

            qs = InventoryMovement.objects.select_related("location", "batch_lot", "batch_lot__product")

            if params.get("date_from"):
                qs = qs.filter(created_at__date__gte=params["date_from"])
            if params.get("date_to"):
                qs = qs.filter(created_at__date__lte=params["date_to"])
            if params.get("location"):
                qs = qs.filter(location_id=params["location"])

            for move in qs:
                writer.writerow([
                    move.created_at.date(),
                    move.location.name,
                    move.batch_lot.product.name,
                    move.batch_lot.batch_no,
                    move.reason,
                    move.qty_change_base,
                ])

    export.file_path = f"/media/exports/{filename}"
    export.finished_at = timezone.now()
    export.save(update_fields=["file_path", "finished_at"])

    return export.file_path
