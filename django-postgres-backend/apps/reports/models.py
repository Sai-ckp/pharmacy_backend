from django.db import models
from django.utils import timezone

class ReportExport(models.Model):
    REPORT_TYPES = [
        ('SALES_REGISTER','SALES_REGISTER'),
        ('H1_REGISTER','H1_REGISTER'),
        ('NDPS_DAILY','NDPS_DAILY'),
        ('STOCK_LEDGER','STOCK_LEDGER'),
    ]
    STATUS = [('QUEUED','QUEUED'),('RUNNING','RUNNING'),('DONE','DONE'),('FAILED','FAILED')]

    report_type = models.CharField(max_length=32, choices=REPORT_TYPES)
    params = models.JSONField()
    status = models.CharField(max_length=16, choices=STATUS, default='QUEUED', db_index=True)
    file_path = models.CharField(max_length=1024, blank=True, null=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
