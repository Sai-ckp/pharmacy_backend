from django.db import models


class Vendor(models.Model):
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Purchase(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    location = models.ForeignKey('locations.Location', on_delete=models.PROTECT)
    vendor_invoice_no = models.CharField(max_length=64, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    gross_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"PO#{self.id} {self.vendor}"


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True)

    qty_packs = models.IntegerField()
    received_base_qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=3)
    mrp = models.DecimalField(max_digits=12, decimal_places=3)


class PurchasePayment(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    mode = models.CharField(max_length=32)
    txn_ref = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField()
    received_by = models.CharField(max_length=64, blank=True)


class PurchaseDocument(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='documents')
    file_url = models.URLField()
    label = models.CharField(max_length=120, blank=True)


class VendorReturn(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    purchase_line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT)
    batch_lot = models.ForeignKey('catalog.BatchLot', on_delete=models.PROTECT)
    qty_base = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=120, blank=True)
    credit_note_no = models.CharField(max_length=64, blank=True)
    credit_note_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

