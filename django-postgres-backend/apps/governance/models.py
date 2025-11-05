from django.db import models


class AuditLog(models.Model):
    actor_user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    table_name = models.CharField(max_length=120)
    record_id = models.CharField(max_length=64)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["table_name", "action", "created_at"], name="idx_audit_table_action_dt"),
        ]


class RetentionPolicy(models.Model):
    module = models.CharField(max_length=120)
    keep_years = models.IntegerField(default=0)
    hold_from_purge = models.BooleanField(default=False)


class SystemEvent(models.Model):
    code = models.CharField(max_length=120)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class BreachLog(models.Model):
    reported_by_user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField()
    severity = models.CharField(max_length=64)
    event_time = models.DateTimeField()

