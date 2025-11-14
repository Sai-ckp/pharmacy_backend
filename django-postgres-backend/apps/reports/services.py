import csv, os, uuid
from django.conf import settings
from django.utils import timezone

from .models import ReportExport
from apps.sales.models import SalesInvoice
from apps.compliance.models import H1RegisterEntry, NDPSDailyEntry
from apps.inventory.models import InventoryMovement
from apps.settingsx.services import get_setting
from apps.inventory.services import near_expiry
from apps.catalog.models import Product


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

        # ------------------------------
        # EXPIRY STATUS REPORT
        # ------------------------------
        elif export.report_type == "EXPIRY_STATUS":
            writer.writerow(["Medicine Name", "Batch Number", "Category", "Quantity", "Stock Value", "Expiry Date", "Days Left", "Status"])
            warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
            rows = near_expiry(days=warn_days, location_id=(params.get("location") if params else None))
            products = {p.id: p for p in Product.objects.filter(id__in=list({r.get("product_id") for r in rows}))}
            from datetime import date as _date
            crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
            today = _date.today()
            for r in rows:
                exp = r.get("expiry_date")
                days_left = (exp - today).days if exp else None
                status_txt = "Safe"
                if days_left is not None:
                    if days_left <= crit_days:
                        status_txt = "Critical"
                    elif days_left <= warn_days:
                        status_txt = "Warning"
                prod = products.get(r.get("product_id"))
                stock_value = ""
                if prod and prod.units_per_pack:
                    try:
                        price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                        stock_value = round(float(r.get("stock_base") or 0) * price_per_base, 2)
                    except Exception:
                        stock_value = ""
                writer.writerow([
                    getattr(prod, 'name', ''),
                    r.get("batch_no"),
                    getattr(getattr(prod, 'category', None), 'name', ''),
                    r.get("stock_base"),
                    stock_value,
                    exp,
                    days_left,
                    status_txt,
                ])

    export.file_path = f"/media/exports/{filename}"
    export.finished_at = timezone.now()
    export.save(update_fields=["file_path", "finished_at"])

    return export.file_path
