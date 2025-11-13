from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

AMOUNT_DECIMAL = dict(max_digits=14, decimal_places=4)


class TransferVoucher(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    from_location = models.ForeignKey(
        'locations.Location',
        on_delete=models.PROTECT,
        related_name='transfer_out_vouchers'
    )
    to_location = models.ForeignKey(
        'locations.Location',
        on_delete=models.PROTECT,
        related_name='transfer_in_vouchers'
    )
    transporter = models.CharField(max_length=255, blank=True, null=True)
    challan_no = models.CharField(max_length=128, blank=True, null=True)
    eway_data = models.JSONField(blank=True, null=True)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )

    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posted_transfer_vouchers'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_transfer_vouchers'
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_transfer_status_created')
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Transfer {self.pk} {self.from_location} → {self.to_location}"


class TransferLine(models.Model):
    voucher = models.ForeignKey(
        TransferVoucher,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    batch_lot = models.ForeignKey(
        'catalog.BatchLot',
        on_delete=models.PROTECT,
        related_name='transfer_lines'
    )
    qty_base = models.DecimalField(**AMOUNT_DECIMAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['voucher'], name='idx_transferline_voucher')]

    def __str__(self):
        return f"{self.voucher} - {self.batch_lot.batch_no} x {self.qty_base}"
