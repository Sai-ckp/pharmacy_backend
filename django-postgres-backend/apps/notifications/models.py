from django.db import models
from django.utils import timezone

class Notification(models.Model):
    CHANNELS = [('EMAIL','EMAIL'),('SMS','SMS'),('PUSH','PUSH'),('WEBHOOK','WEBHOOK')]
    STATUS = [('QUEUED','QUEUED'),('SENT','SENT'),('FAILED','FAILED')]

    channel = models.CharField(max_length=16, choices=CHANNELS)
    to = models.CharField(max_length=1024)
    subject = models.CharField(max_length=512, blank=True, null=True)
    message = models.TextField()
    payload = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=16, choices=STATUS, default='QUEUED', db_index=True)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)