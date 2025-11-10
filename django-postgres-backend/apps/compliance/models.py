from django.db import models
from django.utils import timezone


class Prescription(models.Model):
    # sale_invoice = models.OneToOneField(
    #     "sales.SalesInvoice",
    #     on_delete=models.CASCADE,
    #     related_name="prescription",
    #     null=True,  # allow temporary null during draft'
    #     blank=True,
    # )
    patient_name = models.CharField(max_length=255)
    patient_age = models.IntegerField(null=True, blank=True)
    prescriber_name = models.CharField(max_length=255)
    prescriber_reg_no = models.CharField(max_length=128)
    rx_image_url = models.URLField(blank=True, null=True)
    schedules_captured = models.CharField(max_length=255, blank=True, null=True)  # e.g. "H,H1,NDPS"
    issue_date = models.DateField()
    valid_till = models.DateField()
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "prescriptions"
        ordering = ["-captured_at"]

    def __str__(self):
        return f"Prescription {self.prescriber_name or ''} ({self.patient_name})"


class H1RegisterEntry(models.Model):
    sale_line = models.ForeignKey("sales.SalesLine", on_delete=models.CASCADE, related_name="h1_entries")
    patient_name = models.CharField(max_length=255)
    prescriber_name = models.CharField(max_length=255)
    prescriber_reg_no = models.CharField(max_length=128)
    entry_date = models.DateField(default=timezone.now)

    class Meta:
        db_table = "h1_register_entries"
        ordering = ["-entry_date"]

    def __str__(self):
        return f"H1 Entry {self.sale_line_id} - {self.entry_date}"


class NDPSDailyEntry(models.Model):
    entry_date = models.DateField(default=timezone.now, db_index=True)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="ndps_entries")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    qty_issued = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    class Meta:
        db_table = "ndps_daily_entries"
        unique_together = ("entry_date", "product")
        ordering = ["entry_date"]

    def __str__(self):
        return f"{self.entry_date} - {self.product.name}"


class RecallEvent(models.Model):
    batch_lot = models.ForeignKey("catalog.BatchLot", on_delete=models.PROTECT)
    reason = models.TextField()
    initiated_by = models.ForeignKey("accounts.User",on_delete=models.PROTECT,null=True, blank=True)  # ✅ allow NULL, avoid default='unknown'
    initiated_on = models.DateField(default=timezone.now)
    status = models.CharField(max_length=16, choices=[("OPEN", "Open"), ("CLOSED", "Closed")], default="OPEN")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "recall_events"
        ordering = ["-initiated_on"]

    def __str__(self):
        return f"Recall for {self.batch_lot.batch_no} ({self.status})"
