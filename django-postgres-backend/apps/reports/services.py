import csv, os, uuid
from django.conf import settings
from django.utils import timezone
from .models import ReportExport
from apps.sales.models import SalesInvoice, SalesLine
from apps.compliance.models import H1RegisterEntry, NDPSDailyEntry
from apps.inventory.models import InventoryMovement

EXPORT_DIR = os.path.join(settings.MEDIA_ROOT, "exports")

def generate_report_file(export: ReportExport):
    os.makedirs(EXPORT_DIR, exist_ok=True)
    filename = f"{uuid.uuid4()}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)

    with open(filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        if export.report_type == "SALES_REGISTER":
            writer.writerow(["Invoice No", "Invoice Date", "Customer", "Product", "Batch", "Qty", "Rate", "Tax %", "Tax Amt", "Line Total", "Net Total"])
            for inv in SalesInvoice.objects.prefetch_related("lines__product", "lines__batch_lot")[:100]:
                for line in inv.lines.all():
                    writer.writerow([
                        inv.invoice_no,
                        inv.invoice_date,
                        getattr(inv.customer, "name", ""),
                        line.product.name,
                        line.batch_lot.batch_no,
                        line.qty_base,
                        line.rate_per_base,
                        line.tax_percent,
                        line.tax_amount,
                        line.line_total,
                        inv.net_total
                    ])

        elif export.report_type == "H1_REGISTER":
            writer.writerow(["Sale Line ID", "Entry Date", "Patient", "Prescriber", "Reg No"])
            for entry in H1RegisterEntry.objects.all():
                writer.writerow([
                    entry.id,
                    entry.entry_date,
                    entry.patient_name,
                    entry.doctor_name,
                    entry.doctor_reg_no
                ])

        elif export.report_type == "NDPS_DAILY":
            writer.writerow(["Date", "Product", "Opening", "Issued", "Closing"])
            for entry in NDPSDailyEntry.objects.all():
                writer.writerow([
                    entry.date,
                    entry.product.name if entry.product else "",
                    entry.opening_qty_base,
                    entry.out_qty_base,
                    entry.closing_qty_base
                ])

        elif export.report_type == "STOCK_LEDGER":
            writer.writerow(["Movement Date", "Location", "Product", "Batch", "Reason", "Qty Change"])
            for move in InventoryMovement.objects.select_related("location", "batch_lot")[:200]:
                writer.writerow([
                    move.created_at.date(),
                    move.location.name,
                    move.batch_lot.product.name,
                    move.batch_lot.batch_no,
                    move.reason,
                    move.qty_change_base
                ])

    export.file_path = f"/media/exports/{filename}"
    export.finished_at = timezone.now()
    export.save(update_fields=["file_path", "finished_at"])
    return export.file_path
