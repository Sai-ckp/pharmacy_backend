# apps/reports/models.py
from django.db import models
from django.utils import timezone

class ReportExport(models.Model):
    class ReportType(models.TextChoices):
        SALES_REGISTER = "SALES_REGISTER", "Sales Register"
        H1_REGISTER = "H1_REGISTER", "H1 Register"
        NDPS_DAILY = "NDPS_DAILY", "NDPS Daily"
        STOCK_LEDGER = "STOCK_LEDGER", "Stock Ledger"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    report_type = models.CharField(max_length=32, choices=ReportType.choices)
    params = models.JSONField(default=dict)  # e.g., {"date_from": "2025-11-01", "date_to": "2025-11-11"}
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    file_path = models.CharField(max_length=1024, blank=True, null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["report_type", "status", "created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.report_type} ({self.status})"
