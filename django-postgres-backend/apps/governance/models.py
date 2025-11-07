from django.db import models


class AuditLog(models.Model):
    actor_user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
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

