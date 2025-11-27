# apps/sales/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        PARTIAL = "PARTIAL", "Partial"
        CREDIT = "CREDIT", "Credit"

    # allow blank so we can auto-generate on create
    invoice_no = models.CharField(max_length=64, unique=True, blank=True, null=True)
    location = models.ForeignKey("locations.Location", on_delete=models.PROTECT)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    invoice_date = models.DateTimeField(default=timezone.now)
    place_of_supply = models.CharField(max_length=64, blank=True, null=True)
    buyer_gstin = models.CharField(max_length=32, blank=True, null=True)

    gross_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    round_off_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    net_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    # new summary/payment fields
    total_paid = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.00"))
    outstanding = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0.00"))

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(blank=True, null=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="posted_invoices"
    )

    payment_type = models.ForeignKey(
        "settingsx.PaymentMethod",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices"
    )
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.CREDIT)

    disclaimers = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "invoice_date"])]
        ordering = ["-invoice_date"]

    def __str__(self):
        return self.invoice_no or f"Invoice:{self.pk}"


class SalesLine(models.Model):
    sale_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    batch_lot = models.ForeignKey("catalog.BatchLot", on_delete=models.PROTECT)
    qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    sold_uom = models.CharField(max_length=8, choices=[("BASE", "Base"), ("PACK", "Pack")])
    rate_per_base = models.DecimalField(max_digits=14, decimal_places=4)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_percent = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    requires_prescription = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product.name} ({self.qty_base})"


class SalesPayment(models.Model):
    sale_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    mode = models.CharField(max_length=64)
    txn_ref = models.CharField(max_length=128, blank=True, null=True)
    received_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Auto-update invoice totals
        try:
            from apps.sales.services import _update_payment_status
            _update_payment_status(self.sale_invoice)
        except Exception:
            pass

    def __str__(self):
        return f"{self.sale_invoice.invoice_no or self.sale_invoice.pk} - {self.amount}"
