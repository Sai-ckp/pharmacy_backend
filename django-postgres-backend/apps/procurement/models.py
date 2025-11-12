from django.db import models


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=32, blank=True)
    contact_phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=120, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    account_no = models.CharField(max_length=64, blank=True)
    ifsc = models.CharField(max_length=32, blank=True)
    notes = models.TextField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Purchase(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    location = models.ForeignKey('locations.Location', on_delete=models.PROTECT)
    vendor_invoice_no = models.CharField(max_length=64, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    gross_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"PO#{self.id} {self.vendor}"


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True)

    qty_packs = models.IntegerField()
    received_base_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    mrp = models.DecimalField(max_digits=14, decimal_places=2)


class PurchasePayment(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=32)
    txn_ref = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField()
    received_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)


class PurchaseDocument(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='documents')
    file_url = models.URLField()
    label = models.CharField(max_length=120, blank=True)


class VendorReturn(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT)
    batch_lot = models.ForeignKey('catalog.BatchLot', on_delete=models.PROTECT)
    qty_base = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=120, blank=True)
    credit_note_no = models.CharField(max_length=64, blank=True)
    credit_note_date = models.DateField(null=True, blank=True)
    class Status(models.TextChoices):
        INITIATED = 'INITIATED', 'INITIATED'
        CREDITED = 'CREDITED', 'CREDITED'
        CLOSED = 'CLOSED', 'CLOSED'

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.INITIATED)
    created_at = models.DateTimeField(auto_now_add=True)


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'DRAFT'
        OPEN = 'OPEN', 'OPEN'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'PARTIALLY_RECEIVED'
        COMPLETED = 'COMPLETED', 'COMPLETED'
        CANCELLED = 'CANCELLED', 'CANCELLED'

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    location = models.ForeignKey('locations.Location', on_delete=models.PROTECT)
    po_number = models.CharField(max_length=64, unique=True)
    order_date = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    gross_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "order_date"], name="idx_po_status_orderdate"),
        ]


class PurchaseOrderLine(models.Model):
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    qty_packs_ordered = models.IntegerField()
    expected_unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    gst_percent_override = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)


class GoodsReceipt(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'DRAFT'
        POSTED = 'POSTED', 'POSTED'
        CANCELLED = 'CANCELLED', 'CANCELLED'

    po = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT)
    location = models.ForeignKey('locations.Location', on_delete=models.PROTECT)
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    supplier_invoice_no = models.CharField(max_length=64, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)


class GoodsReceiptLine(models.Model):
    grn = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='lines')
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT)
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    batch_no = models.CharField(max_length=64)
    mfg_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    qty_packs_received = models.IntegerField()
    qty_base_received = models.DecimalField(max_digits=14, decimal_places=3)
    qty_base_damaged = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    mrp = models.DecimalField(max_digits=14, decimal_places=2)

