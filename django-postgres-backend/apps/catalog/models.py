from django.db import models


class ProductCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    hsn = models.CharField(max_length=32, blank=True)
    schedule = models.CharField(max_length=32, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    mrp = models.DecimalField(max_digits=12, decimal_places=3, help_text="MRP per pack")
    is_sensitive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # unit-aware
    base_unit = models.CharField(max_length=32)
    pack_unit = models.CharField(max_length=32)
    units_per_pack = models.DecimalField(max_digits=12, decimal_places=3)
    base_unit_step = models.DecimalField(max_digits=12, decimal_places=3, default=1)

    # optional
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class BatchLot(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "ACTIVE"
        EXPIRED = "EXPIRED", "EXPIRED"
        RETURNED = "RETURNED", "RETURNED"
        BLOCKED = "BLOCKED", "BLOCKED"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    rack_no = models.CharField(max_length=64, blank=True)
    recall_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "batch_no"], name="uq_batch_product_batchno"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}:{self.batch_no}"

