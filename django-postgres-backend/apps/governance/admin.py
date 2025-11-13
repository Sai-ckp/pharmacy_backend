from django.contrib import admin
from .models import AuditLog, RetentionPolicy, SystemEvent, BreachLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "actor_user", "action", "table_name", "record_id", "created_at")
    list_filter = ("action", "table_name")


admin.site.register(RetentionPolicy)
admin.site.register(SystemEvent)
admin.site.register(BreachLog)

