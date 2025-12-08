from django.contrib import admin
from .models import ExampleModel, SystemLicense


@admin.register(ExampleModel)
class ExampleModelAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")


@admin.register(SystemLicense)
class SystemLicenseAdmin(admin.ModelAdmin):
    list_display = ("license_key", "status", "valid_from", "valid_to", "is_active_flag", "days_left")
    list_filter = ("status",)
    search_fields = ("license_key",)
    readonly_fields = ("created_at", "updated_at")

    def is_active_flag(self, obj):
        return obj.is_active

    is_active_flag.boolean = True
    is_active_flag.short_description = "Is active"
