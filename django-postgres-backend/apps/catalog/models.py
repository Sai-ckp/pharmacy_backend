from django.db import models
from django.utils import timezone


class ProductCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Schedule(models.TextChoices):
        OTC = "OTC", "OTC"
        H = "H", "H"
        H1 = "H1", "H1"
        X = "X", "X"
        NDPS = "NDPS", "NDPS"

    code = models.CharField(max_length=64, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    dosage_strength = models.CharField(max_length=64, blank=True)
    hsn = models.CharField(max_length=32, blank=True)
    schedule = models.CharField(max_length=8, choices=Schedule.choices, default=Schedule.OTC)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True)
    pack_size = models.CharField(max_length=64, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    mrp = models.DecimalField(max_digits=14, decimal_places=2, help_text="MRP per pack")
    base_unit = models.CharField(max_length=32)
    pack_unit = models.CharField(max_length=32)
    units_per_pack = models.DecimalField(max_digits=14, decimal_places=3)
    base_unit_step = models.DecimalField(max_digits=14, decimal_places=3, default=1.000)
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    description = models.TextField(blank=True)
    storage_instructions = models.TextField(blank=True)
    preferred_vendor = models.ForeignKey('procurement.Vendor', on_delete=models.SET_NULL, null=True, blank=True)
    is_sensitive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"], name="idx_product_code"),
            models.Index(fields=["name"], name="idx_product_name"),
            models.Index(fields=["manufacturer"], name="idx_product_mfr"),
            models.Index(fields=["is_active"], name="idx_product_active"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        # Basic validations per spec
        if self.units_per_pack is not None and self.units_per_pack <= 0:
            raise ValueError("units_per_pack must be > 0")
        if self.base_unit_step is not None and self.base_unit_step <= 0:
            raise ValueError("base_unit_step must be > 0")
        if self.reorder_level is not None and self.reorder_level < 0:
            raise ValueError("reorder_level must be >= 0")
        super().save(*args, **kwargs)


class MedicineForm(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=512, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="idx_form_name"),
            models.Index(fields=["is_active"], name="idx_form_active"),
        ]

    def __str__(self) -> str:
        return self.name


class Uom(models.Model):
    class UomType(models.TextChoices):
        BASE = "BASE", "BASE"
        PACK = "PACK", "PACK"
        BOTH = "BOTH", "BOTH"

    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=512, null=True, blank=True)
    uom_type = models.CharField(max_length=8, choices=UomType.choices, default=UomType.BOTH)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="idx_uom_name"),
            models.Index(fields=["is_active"], name="idx_uom_active"),
        ]

    def __str__(self) -> str:
        return self.name


class VendorProductCode(models.Model):
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    vendor_code = models.CharField(max_length=120)
    vendor_name_alias = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["vendor", "vendor_code"], name="uq_vendor_code"),
        ]

    def __str__(self) -> str:
        return f"{self.vendor_id}:{self.vendor_code} -> {self.product_id}"


class BatchLot(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "ACTIVE"
        EXPIRED = "EXPIRED", "EXPIRED"
        RETURNED = "RETURNED", "RETURNED"
        BLOCKED = "BLOCKED", "BLOCKED"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    batch_no = models.CharField(max_length=64)
    mfg_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    recall_reason = models.TextField(blank=True)
    rack_no = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "batch_no"], name="uq_batch_product_batchno"),
        ]
        indexes = [
            models.Index(fields=["product", "status", "expiry_date"], name="idx_lot_product_status_exp"),
            models.Index(fields=["status", "expiry_date"], name="idx_lot_status_exp"),
            models.Index(fields=["product", "expiry_date"], name="idx_lot_product_exp"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}:{self.batch_no}"

    def save(self, *args, **kwargs):
        if self.expiry_date and self.expiry_date < timezone.now().date():
            self.status = BatchLot.Status.EXPIRED
        super().save(*args, **kwargs)

