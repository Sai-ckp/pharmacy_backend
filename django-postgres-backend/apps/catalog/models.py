from decimal import Decimal

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
    medicine_form = models.ForeignKey("catalog.MedicineForm", on_delete=models.SET_NULL, null=True, blank=True)
    base_uom = models.ForeignKey('catalog.Uom', on_delete=models.PROTECT, null=True, blank=True, related_name='products_as_base')
    selling_uom = models.ForeignKey('catalog.Uom', on_delete=models.PROTECT, null=True, blank=True, related_name='products_as_selling')
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
    rack_location = models.ForeignKey('inventory.RackLocation', on_delete=models.PROTECT, null=True, blank=True)
    preferred_vendor = models.ForeignKey('procurement.Vendor', on_delete=models.SET_NULL, null=True, blank=True)
    is_sensitive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Tablet/Capsule packaging
    tablets_per_strip = models.PositiveIntegerField(null=True, blank=True)
    capsules_per_strip = models.PositiveIntegerField(null=True, blank=True)
    strips_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Liquid packaging
    ml_per_bottle = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    bottles_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Injection/Vial packaging
    ml_per_vial = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    vials_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Ointment/Cream/Gel packaging
    grams_per_tube = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    tubes_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Inhaler packaging
    doses_per_inhaler = models.PositiveIntegerField(null=True, blank=True)
    inhalers_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Powder/Sachet packaging
    grams_per_sachet = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    sachets_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Soap/Bar packaging
    grams_per_bar = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    bars_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Pack/Generic packaging
    pieces_per_pack = models.PositiveIntegerField(null=True, blank=True)
    packs_per_box = models.PositiveIntegerField(null=True, blank=True)
    # Gloves/Pairs packaging
    pairs_per_pack = models.PositiveIntegerField(null=True, blank=True)
    # Cotton/Gauze packaging
    grams_per_pack = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

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
        
        # Tablet/Capsule validations
        if self.tablets_per_strip is not None and self.tablets_per_strip <= 0:
            raise ValueError("tablets_per_strip must be > 0")
        if self.capsules_per_strip is not None and self.capsules_per_strip <= 0:
            raise ValueError("capsules_per_strip must be > 0")
        if self.strips_per_box is not None and self.strips_per_box <= 0:
            raise ValueError("strips_per_box must be > 0")
        
        # Liquid validations
        if self.ml_per_bottle is not None and self.ml_per_bottle <= 0:
            raise ValueError("ml_per_bottle must be > 0")
        if self.bottles_per_box is not None and self.bottles_per_box <= 0:
            raise ValueError("bottles_per_box must be > 0")
        
        # Injection/Vial validations
        if self.ml_per_vial is not None and self.ml_per_vial <= 0:
            raise ValueError("ml_per_vial must be > 0")
        if self.vials_per_box is not None and self.vials_per_box <= 0:
            raise ValueError("vials_per_box must be > 0")
        
        # Ointment/Cream/Gel validations
        if self.grams_per_tube is not None and self.grams_per_tube <= 0:
            raise ValueError("grams_per_tube must be > 0")
        if self.tubes_per_box is not None and self.tubes_per_box <= 0:
            raise ValueError("tubes_per_box must be > 0")
        
        # Inhaler validations
        if self.doses_per_inhaler is not None and self.doses_per_inhaler <= 0:
            raise ValueError("doses_per_inhaler must be > 0")
        if self.inhalers_per_box is not None and self.inhalers_per_box <= 0:
            raise ValueError("inhalers_per_box must be > 0")
        
        # Powder/Sachet validations
        if self.grams_per_sachet is not None and self.grams_per_sachet <= 0:
            raise ValueError("grams_per_sachet must be > 0")
        if self.sachets_per_box is not None and self.sachets_per_box <= 0:
            raise ValueError("sachets_per_box must be > 0")
        
        # Soap/Bar validations
        if self.grams_per_bar is not None and self.grams_per_bar <= 0:
            raise ValueError("grams_per_bar must be > 0")
        if self.bars_per_box is not None and self.bars_per_box <= 0:
            raise ValueError("bars_per_box must be > 0")
        
        # Pack/Generic validations
        if self.pieces_per_pack is not None and self.pieces_per_pack <= 0:
            raise ValueError("pieces_per_pack must be > 0")
        if self.packs_per_box is not None and self.packs_per_box <= 0:
            raise ValueError("packs_per_box must be > 0")
        
        # Gloves/Pairs validations
        if self.pairs_per_pack is not None and self.pairs_per_pack <= 0:
            raise ValueError("pairs_per_pack must be > 0")
        
        # Cotton/Gauze validations
        if self.grams_per_pack is not None and self.grams_per_pack <= 0:
            raise ValueError("grams_per_pack must be > 0")

        # Keep legacy unit char fields in sync with master tables when possible
        if self.base_uom_id and getattr(self.base_uom, "name", None):
            self.base_unit = self.base_uom.name
        elif not self.base_uom_id and self.base_unit:
            try:
                self.base_uom = Uom.objects.get(name__iexact=self.base_unit)
            except Uom.DoesNotExist:
                pass

        if self.selling_uom_id and getattr(self.selling_uom, "name", None):
            self.pack_unit = self.selling_uom.name
        elif not self.selling_uom_id and self.pack_unit:
            try:
                self.selling_uom = Uom.objects.get(name__iexact=self.pack_unit)
            except Uom.DoesNotExist:
                pass

        super().save(*args, **kwargs)

#changing the medicineFrom to the HSN code 
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
    quantity_uom = models.ForeignKey('catalog.Uom', on_delete=models.PROTECT, null=True, blank=True, related_name='batch_quantity_uoms')
    initial_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    initial_quantity_base = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0.000"))
    purchase_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    purchase_price_per_base = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("0.000000"))
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
        if self.initial_quantity is not None and self.initial_quantity < 0:
            raise ValueError("initial_quantity must be >= 0")
        if self.initial_quantity_base is not None and self.initial_quantity_base < 0:
            raise ValueError("initial_quantity_base must be >= 0")
        if self.purchase_price is not None and self.purchase_price < 0:
            raise ValueError("purchase_price must be >= 0")
        if self.purchase_price_per_base is not None and self.purchase_price_per_base < 0:
            raise ValueError("purchase_price_per_base must be >= 0")
        super().save(*args, **kwargs)

