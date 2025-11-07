from django.db import models


class InventoryMovement(models.Model):
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
    qty_change_base = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    ref_doc_type = models.CharField(max_length=32, blank=True)
    ref_doc_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["location", "batch_lot", "created_at"], name="idx_move_loc_batch_dt"),
        ]


class RackRule(models.Model):
    location = models.ForeignKey('locations.Location', on_delete=models.CASCADE)
    manufacturer_name = models.CharField(max_length=200)
    rack_code = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["location", "manufacturer_name"], name="uq_rack_location_manufacturer"),
        ]

