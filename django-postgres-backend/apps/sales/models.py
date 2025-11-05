from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        POSTED = "POSTED"
        CANCELLED = "CANCELLED"

    class PaymentStatus(models.TextChoices):
        PAID = "PAID"
        PARTIAL = "PARTIAL"
        CREDIT = "CREDIT"

    invoice_no = models.CharField(max_length=64, unique=True)
    financial_year = models.CharField(max_length=16, db_index=True)
    location = models.ForeignKey("locations.Location", on_delete=models.PROTECT)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    invoice_date = models.DateTimeField(default=timezone.now)
    place_of_supply = models.CharField(max_length=8)

    patient_name = models.CharField(max_length=255, blank=True, null=True)
    patient_age = models.CharField(max_length=16, blank=True, null=True)
    doctor_name = models.CharField(max_length=255, blank=True, null=True)
    doctor_reg_no = models.CharField(max_length=64, blank=True, null=True)
    prescription = models.ForeignKey(
        "compliance.Prescription", on_delete=models.SET_NULL, null=True, blank=True
    )

    gross_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    round_off = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    net_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="posted_invoices"
    )
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.CREDIT)

    irn = models.CharField(max_length=128, blank=True, null=True)
    ack_no = models.CharField(max_length=128, blank=True, null=True)
    ack_date = models.DateTimeField(null=True, blank=True)

    disclaimers = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "invoice_date"])]

    def __str__(self):
        return self.invoice_no


class SalesLine(models.Model):
    sale_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    batch_lot = models.ForeignKey("catalog.BatchLot", on_delete=models.PROTECT)
    qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    free_qty_base = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    sold_uom = models.CharField(max_length=8, choices=[("BASE", "BASE"), ("PACK", "PACK")])
    rate_per_base = models.DecimalField(max_digits=14, decimal_places=4)
    discount_percent = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_percent = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    hsn_code = models.CharField(max_length=64, blank=True, null=True)
    batch_no = models.CharField(max_length=64, blank=True, null=True)
    expiry_date = models.DateField(null=True, blank=True)
    product_name = models.CharField(max_length=255, blank=True, null=True)
    pack_text = models.CharField(max_length=128, blank=True, null=True)
    mrp = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    ptr = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    pts = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    requires_prescription = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product_name or self.product.name}"


class SalesPayment(models.Model):
    sale_invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    mode = models.CharField(max_length=64)
    txn_ref = models.CharField(max_length=128, blank=True, null=True)
    received_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    def __str__(self): return f"{self.sale_invoice.invoice_no}-{self.amount}"
