from django.db import models
from django.utils import timezone

class Prescription(models.Model):
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='prescriptions')
    doctor_name = models.CharField(max_length=255)
    doctor_reg_no = models.CharField(max_length=128)
    prescription_no = models.CharField(max_length=128)
    issue_date = models.DateField()
    valid_till = models.DateField()
    attachment_url = models.URLField(blank=True, null=True)
    captured_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

from django.db import models
from django.utils import timezone


class H1RegisterEntry(models.Model):
    # 🟡 Temporarily made nullable to avoid migration errors — can set to null=False later
    invoice = models.ForeignKey(
        'sales.SalesInvoice',
        on_delete=models.CASCADE,
        related_name='h1_entries',
        null=True, blank=True  # ← Make this strict (remove null=True, blank=True) later
    )

    # 🟡 Temporarily nullable
    line = models.ForeignKey(
        'sales.SalesLine',
        on_delete=models.CASCADE,
        null=True, blank=True  # ← Remove null=True, blank=True after successful migration
    )

    # 🟡 Temporarily nullable
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        null=True, blank=True  # ← Remove later
    )

    # 🟡 Temporarily nullable
    batch_lot = models.ForeignKey(
        'catalog.BatchLot',
        on_delete=models.PROTECT,
        null=True, blank=True  # ← Remove later
    )

    # 🟢 These snapshots can safely stay nullable — they are not required for DB integrity
    drug_name_snapshot = models.CharField(max_length=255, null=True, blank=True)
    batch_no_snapshot = models.CharField(max_length=64, null=True, blank=True)
    expiry_snapshot = models.DateField(null=True, blank=True)

    # 🟢 Patient details (can stay optional)
    patient_name = models.CharField(max_length=255, null=True, blank=True)
    patient_address = models.TextField(null=True, blank=True)

    # 🟡 Temporarily nullable — remove after migration if you want strict validation
    doctor_name = models.CharField(max_length=255, null=True, blank=True)  # ← Remove nullg=True, blank=True later
    doctor_reg_no = models.CharField(max_length=128, null=True, blank=True)  # ← Remove later

    # 🟢 Quantity fields (optional, safe to keep nullable)
    qty_issued_base = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    balance_after_issue_base = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    # ✅ Default can remain (no change needed)
    entry_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"H1 Entry for {self.product or 'Unknown Product'}"


class NDPSDailyEntry(models.Model):
    date = models.DateField()
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    opening_qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    in_qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    out_qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    closing_qty_base = models.DecimalField(max_digits=14, decimal_places=4)
    remarks = models.TextField(blank=True, null=True)

class RecallEvent(models.Model):
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT)
    batch_lot = models.ForeignKey('catalog.BatchLot', on_delete=models.PROTECT)
    reason = models.TextField()
    initiated_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=8, choices=[('OPEN','OPEN'),('CLOSED','CLOSED')], default='OPEN')
    notes = models.TextField(blank=True, null=True)
