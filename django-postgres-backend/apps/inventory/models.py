from django.db import models


class InventoryLedger(models.Model):
    class Reason(models.TextChoices):
        PURCHASE = "PURCHASE", "PURCHASE"
        SALE = "SALE", "SALE"
        ADJUSTMENT = "ADJUSTMENT", "ADJUSTMENT"
        TRANSFER_OUT = "TRANSFER_OUT", "TRANSFER_OUT"
        TRANSFER_IN = "TRANSFER_IN", "TRANSFER_IN"
        RETURN_VENDOR = "RETURN_VENDOR", "RETURN_VENDOR"
        WRITE_OFF = "WRITE_OFF", "WRITE_OFF"
        RECALL_BLOCK = "RECALL_BLOCK", "RECALL_BLOCK"

    location = models.ForeignKey('locations.Location', on_delete=models.CASCADE)
    batch_lot = models.ForeignKey('catalog.BatchLot', on_delete=models.CASCADE)
    qty_change_base = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    ref_doc_type = models.CharField(max_length=32, blank=True)
    ref_doc_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["location", "batch_lot"], name="idx_ledger_loc_batch"),
        ]

