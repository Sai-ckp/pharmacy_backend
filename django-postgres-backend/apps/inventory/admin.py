from django.contrib import admin
from .models import InventoryLedger


@admin.register(InventoryLedger)
class InventoryLedgerAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "batch_lot", "qty_change_base", "reason", "created_at")
    list_filter = ("reason", "location")

