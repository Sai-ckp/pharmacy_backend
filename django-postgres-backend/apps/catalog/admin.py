from django.contrib import admin
from .models import ProductCategory, Product, BatchLot


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "manufacturer", "mrp", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "manufacturer", "hsn")


@admin.register(BatchLot)
class BatchLotAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "batch_no", "expiry_date", "status", "rack_no")
    list_filter = ("status",)
    search_fields = ("batch_no",)

