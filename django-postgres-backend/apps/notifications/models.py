from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        PUSH = "PUSH", "Push Notification"
        WEBHOOK = "WEBHOOK", "Webhook"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    channel = models.CharField(max_length=16, choices=Channel.choices)
    to = models.CharField(max_length=1024)
    subject = models.CharField(max_length=512, blank=True, null=True)
    message = models.TextField()
    payload = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["channel", "status", "created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} → {self.to} ({self.status})"
