from django.contrib import admin
from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "type", "is_active")
    search_fields = ("code", "name")

