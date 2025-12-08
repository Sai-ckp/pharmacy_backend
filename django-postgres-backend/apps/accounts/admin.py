from django.contrib import admin

from .models import UserDevice


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "device_id", "last_login_at")
    search_fields = ("user__username", "user__email", "device_id")

