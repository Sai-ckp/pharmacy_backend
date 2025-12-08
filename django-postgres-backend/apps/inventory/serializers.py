from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.catalog.models import ProductCategory, Product, MedicineForm, Uom
from .models import InventoryMovement, RackLocation
from .services import (
    BOX_NAMES,
    BOTTLE_NAMES,
    GM_BASE_NAMES,
    ML_BASE_NAMES,
    STRIP_NAMES,
    TAB_BASE_NAMES,
    TUBE_NAMES,
    VIAL_BASE_NAMES,
    convert_quantity_to_base,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Name already exists"


class InventoryLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = "__all__"


class RackLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RackLocation
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        max_capacity = attrs.get("max_capacity", getattr(self.instance, "max_capacity", None))
        current_capacity = attrs.get("current_capacity", getattr(self.instance, "current_capacity", 0))
        if max_capacity is not None and max_capacity < 0:
            raise serializers.ValidationError({"max_capacity": "Must be non-negative."})
        if current_capacity is not None and current_capacity < 0:
            raise serializers.ValidationError({"current_capacity": "Must be non-negative."})
        if max_capacity is not None and current_capacity is not None and current_capacity > max_capacity:
            raise serializers.ValidationError({"current_capacity": "Cannot exceed max_capacity."})
        qs = RackLocation.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        return attrs


class MasterRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class MedicinePayloadSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=200)
    generic_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    category = serializers.CharField(max_length=120)  # Accept string category name or ID
    form = serializers.PrimaryKeyRelatedField(queryset=MedicineForm.objects.all(), source="medicine_form", required=False)
    strength = serializers.CharField(max_length=64, required=False, allow_blank=True)
    base_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all(), required=False)
    selling_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all(), required=False)
    rack_location = serializers.PrimaryKeyRelatedField(queryset=RackLocation.objects.all(), required=False)
    # Tablet/Capsule packaging
    tablets_per_strip = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    capsules_per_strip = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    strips_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Liquid packaging
    ml_per_bottle = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    bottles_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Injection/Vial packaging
    ml_per_vial = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    vials_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Ointment/Cream/Gel packaging
    grams_per_tube = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    tubes_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Inhaler packaging
    doses_per_inhaler = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    inhalers_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Powder/Sachet packaging
    grams_per_sachet = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    sachets_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Soap/Bar packaging
    grams_per_bar = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    bars_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Pack/Generic packaging
    pieces_per_pack = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    packs_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Gloves/Pairs packaging
    pairs_per_pack = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    # Cotton/Gauze packaging
    grams_per_pack = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    gst_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    mrp = serializers.DecimalField(max_digits=14, decimal_places=2)
    units_per_pack = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)

    def validate_id(self, value):
        if value and not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid medicine id.")
        return value

    def validate_category(self, value):
        """Convert frontend category string ID to ProductCategory instance"""
        # Mapping from frontend category string IDs to database category names
        CATEGORY_MAPPING = {
            'tablet': 'Tablet',
            'capsule': 'Capsule',
            'syrup': 'Syrup/Suspension',
            'injection': 'Injection/Vial',
            'ointment': 'Ointment/Cream',
            'drops': 'Drops (Eye/Ear/Nasal)',
            'inhaler': 'Inhaler',
            'powder': 'Powder/Sachet',
            'gel': 'Gel',
            'spray': 'Spray',
            'lotion': 'Lotion/Solution',
            'shampoo': 'Shampoo',
            'soap': 'Soap/Bar',
            'bandage': 'Bandage/Dressing',
            'mask': 'Mask (Surgical/N95)',
            'gloves': 'Gloves',
            'cotton': 'Cotton/Gauze',
            'sanitizer': 'Hand Sanitizer',
            'thermometer': 'Thermometer',
            'supplement': 'Supplement/Vitamin',
            'other': 'Other/Miscellaneous',
        }
        
        try:
            # Try to treat as integer ID first
            category_id = int(value)
            category = ProductCategory.objects.filter(id=category_id).first()
            if category:
                return category
            raise serializers.ValidationError(f"Invalid category ID: {category_id}")
        except (ValueError, TypeError):
            # Map frontend string ID to database category name
            category_name = None
            if value in CATEGORY_MAPPING:
                category_name = CATEGORY_MAPPING[value]
            else:
                # If not in mapping, try the value as category name directly
                category_name = value
            
            # Find or create the category
            category, created = ProductCategory.objects.get_or_create(
                name=category_name,
                defaults={'is_active': True}
            )
            return category

    def validate(self, attrs):
        attrs["name"] = (attrs.get("name") or "").strip()
        if not attrs["name"]:
            raise serializers.ValidationError({"name": "This field is required."})
        if "generic_name" in attrs:
            attrs["generic_name"] = (attrs.get("generic_name") or "").strip()
        if "strength" in attrs:
            attrs["strength"] = (attrs.get("strength") or "").strip()
        if "description" in attrs:
            attrs["description"] = attrs.get("description") or ""

        units_per_pack = attrs.get("units_per_pack")
        tablets_per_strip = attrs.get("tablets_per_strip")
        capsules_per_strip = attrs.get("capsules_per_strip")
        strips_per_box = attrs.get("strips_per_box")
        ml_per_bottle = attrs.get("ml_per_bottle")
        bottles_per_box = attrs.get("bottles_per_box")
        vials_per_box = attrs.get("vials_per_box")
        ml_per_vial = attrs.get("ml_per_vial")
        grams_per_tube = attrs.get("grams_per_tube")
        tubes_per_box = attrs.get("tubes_per_box")
        grams_per_sachet = attrs.get("grams_per_sachet")
        sachets_per_box = attrs.get("sachets_per_box")
        grams_per_bar = attrs.get("grams_per_bar")
        bars_per_box = attrs.get("bars_per_box")
        pieces_per_pack = attrs.get("pieces_per_pack")
        packs_per_box = attrs.get("packs_per_box")
        pairs_per_pack = attrs.get("pairs_per_pack")
        grams_per_pack = attrs.get("grams_per_pack")
        doses_per_inhaler = attrs.get("doses_per_inhaler")
        inhalers_per_box = attrs.get("inhalers_per_box")
        
        # Convert decimal fields
        if units_per_pack is not None:
            units_per_pack = Decimal(str(units_per_pack))
        decimal_fields = ("ml_per_bottle", "ml_per_vial", "grams_per_tube", "grams_per_sachet", "grams_per_bar", "grams_per_pack")
        for field in decimal_fields:
            if attrs.get(field) in (None, ""):
                attrs[field] = None
            else:
                attrs[field] = Decimal(str(attrs[field]))
        
        # Re-read after conversion
        ml_per_bottle = attrs.get("ml_per_bottle")
        ml_per_vial = attrs.get("ml_per_vial")
        grams_per_tube = attrs.get("grams_per_tube")
        grams_per_sachet = attrs.get("grams_per_sachet")
        grams_per_bar = attrs.get("grams_per_bar")
        grams_per_pack = attrs.get("grams_per_pack")
        
        # Calculate units_per_pack from packaging fields (new frontend approach)
        inferred = self._calculate_units_per_pack_from_packaging(
            provided=units_per_pack,
            tablets_per_strip=tablets_per_strip,
            capsules_per_strip=capsules_per_strip,
            strips_per_box=strips_per_box,
            ml_per_bottle=ml_per_bottle,
            bottles_per_box=bottles_per_box,
            ml_per_vial=ml_per_vial,
            vials_per_box=vials_per_box,
            grams_per_tube=grams_per_tube,
            tubes_per_box=tubes_per_box,
            grams_per_sachet=grams_per_sachet,
            sachets_per_box=sachets_per_box,
            grams_per_bar=grams_per_bar,
            bars_per_box=bars_per_box,
            pieces_per_pack=pieces_per_pack,
            packs_per_box=packs_per_box,
            pairs_per_pack=pairs_per_pack,
            grams_per_pack=grams_per_pack,
            doses_per_inhaler=doses_per_inhaler,
            inhalers_per_box=inhalers_per_box,
        )
        
        if inferred is None:
            # Default to 1 if we can't calculate (for backward compatibility)
            inferred = Decimal("1.000")
        
        attrs["units_per_pack"] = inferred

        gst_percent = attrs.get("gst_percent")
        attrs["gst_percent"] = Decimal(str(gst_percent or 0))
        attrs["mrp"] = Decimal(str(attrs.get("mrp")))
        self._enforce_packaging_rules(attrs)
        return attrs

    @staticmethod
    def _calculate_units_per_pack_from_packaging(
        *,
        provided: Decimal | None,
        tablets_per_strip: int | None,
        capsules_per_strip: int | None,
        strips_per_box: int | None,
        ml_per_bottle: Decimal | None,
        bottles_per_box: int | None,
        ml_per_vial: Decimal | None,
        vials_per_box: int | None,
        grams_per_tube: Decimal | None,
        tubes_per_box: int | None,
        grams_per_sachet: Decimal | None,
        sachets_per_box: int | None,
        grams_per_bar: Decimal | None,
        bars_per_box: int | None,
        pieces_per_pack: int | None,
        packs_per_box: int | None,
        pairs_per_pack: int | None,
        grams_per_pack: Decimal | None,
        doses_per_inhaler: int | None,
        inhalers_per_box: int | None,
    ) -> Decimal | None:
        """Calculate units_per_pack directly from packaging fields (new frontend approach)"""
        if provided is not None and provided > 0:
            return provided
        
        # Tablet/Capsule: tablets_per_strip * strips_per_box (if box) or tablets_per_strip (if strip)
        if tablets_per_strip:
            if strips_per_box:
                return Decimal(tablets_per_strip) * Decimal(strips_per_box)
            return Decimal(tablets_per_strip)
        
        if capsules_per_strip:
            if strips_per_box:
                return Decimal(capsules_per_strip) * Decimal(strips_per_box)
            return Decimal(capsules_per_strip)
        
        # Liquid: ml_per_bottle * bottles_per_box (if box) or ml_per_bottle (if bottle)
        if ml_per_bottle:
            if bottles_per_box:
                return ml_per_bottle * Decimal(bottles_per_box)
            return ml_per_bottle
        
        # Injection/Vial: ml_per_vial * vials_per_box (if box) or ml_per_vial (if vial)
        if ml_per_vial:
            if vials_per_box:
                return ml_per_vial * Decimal(vials_per_box)
            return ml_per_vial
        
        # Ointment/Cream/Gel: grams_per_tube * tubes_per_box (if box) or grams_per_tube (if tube)
        if grams_per_tube:
            if tubes_per_box:
                return grams_per_tube * Decimal(tubes_per_box)
            return grams_per_tube
        
        # Powder/Sachet: grams_per_sachet * sachets_per_box (if box) or grams_per_sachet (if sachet)
        if grams_per_sachet:
            if sachets_per_box:
                return grams_per_sachet * Decimal(sachets_per_box)
            return grams_per_sachet
        
        # Soap/Bar: grams_per_bar * bars_per_box (if box) or grams_per_bar (if bar)
        if grams_per_bar:
            if bars_per_box:
                return grams_per_bar * Decimal(bars_per_box)
            return grams_per_bar
        
        # Pack/Generic: pieces_per_pack * packs_per_box (if box) or pieces_per_pack (if pack)
        if pieces_per_pack:
            if packs_per_box:
                return Decimal(pieces_per_pack) * Decimal(packs_per_box)
            return Decimal(pieces_per_pack)
        
        # Gloves: pairs_per_pack * packs_per_box (if box) or pairs_per_pack (if pack)
        if pairs_per_pack:
            if packs_per_box:
                return Decimal(pairs_per_pack) * Decimal(packs_per_box)
            return Decimal(pairs_per_pack)
        
        # Cotton/Gauze: grams_per_pack * packs_per_box (if box) or grams_per_pack (if pack)
        if grams_per_pack:
            if packs_per_box:
                return grams_per_pack * Decimal(packs_per_box)
            return grams_per_pack
        
        # Inhaler: doses_per_inhaler * inhalers_per_box (if box) or doses_per_inhaler (if inhaler)
        if doses_per_inhaler:
            if inhalers_per_box:
                return Decimal(doses_per_inhaler) * Decimal(inhalers_per_box)
            return Decimal(doses_per_inhaler)
        
        # Vials per box (for injection)
        if vials_per_box:
            return Decimal(vials_per_box)
        
        # Default: return None (will be set to 1.000 in validate method)
        return None

    def _enforce_packaging_rules(self, attrs: dict) -> None:
        """Enforce packaging rules based on category - relaxed for new frontend approach"""
        # With new frontend, packaging fields are optional and validated by category
        # This method is kept for backward compatibility but doesn't enforce strict rules
        # The frontend handles category-specific field requirements
        pass


class MedicineBatchInputSerializer(serializers.Serializer):
    batch_number = serializers.CharField(max_length=64)
    mfg_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=0)
    quantity_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all(), required=False, allow_null=True)
    stock_unit = serializers.ChoiceField(choices=['box', 'loose'], required=False, allow_blank=True)
    purchase_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)

    def validate_batch_number(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("This field is required.")
        return value

    def validate(self, attrs):
        mfg = attrs.get("mfg_date")
        expiry = attrs.get("expiry_date")
        if mfg and expiry and mfg > expiry:
            raise serializers.ValidationError({"expiry_date": "Expiry must be after manufacture date."})
        if expiry and expiry < timezone.now().date():
            # Allow creation but inform API consumer
            raise serializers.ValidationError({"expiry_date": "Expiry date cannot be in the past."})
        purchase_price = attrs.get("purchase_price")
        if purchase_price is not None:
            attrs["purchase_price"] = Decimal(str(purchase_price))
        attrs["quantity"] = int(attrs.get("quantity"))
        return attrs


class MedicineBatchUpdateSerializer(MedicineBatchInputSerializer):
    id = serializers.IntegerField()


class AddMedicineRequestSerializer(serializers.Serializer):
    location_id = serializers.IntegerField(required=False)
    medicine = MedicinePayloadSerializer()
    batch = MedicineBatchInputSerializer()

    def _infer_quantity_uom(self, stock_unit, category_id, medicine_data):
        """Infer quantity_uom from stock_unit and category"""
        from apps.catalog.models import Uom, ProductCategory
        
        if not stock_unit:
            return None
        
        # Get category name
        category_name = None
        if category_id:
            try:
                if isinstance(category_id, ProductCategory):
                    category_name = category_id.name
                elif isinstance(category_id, int):
                    category = ProductCategory.objects.filter(id=category_id).first()
                    if category:
                        category_name = category.name
                elif hasattr(category_id, 'name'):
                    category_name = category_id.name
                else:
                    category_name = str(category_id)
            except:
                pass
        
        # Map category to UOM names based on stock_unit
        uom_name = None
        
        if stock_unit == "box":
            # For box, always use BOX UOM
            uom_name = "BOX"
        elif stock_unit == "loose":
            # For loose, determine based on category
            if category_name:
                category_lower = category_name.lower()
                if "tablet" in category_lower or "capsule" in category_lower or "supplement" in category_lower:
                    uom_name = "STRIP"
                elif "syrup" in category_lower or "suspension" in category_lower or "drops" in category_lower or "spray" in category_lower or "lotion" in category_lower or "shampoo" in category_lower or "sanitizer" in category_lower:
                    uom_name = "BOTTLE"
                elif "injection" in category_lower or "vial" in category_lower:
                    uom_name = "VIAL"
                elif "ointment" in category_lower or "cream" in category_lower or "gel" in category_lower:
                    uom_name = "TUBE"
                elif "powder" in category_lower or "sachet" in category_lower:
                    uom_name = "PACK"  # Sachets are typically sold as packs
                elif "inhaler" in category_lower:
                    uom_name = "INHALER"
                elif "soap" in category_lower or "bar" in category_lower:
                    uom_name = "PACK"  # Bars are typically sold as packs
                elif "bandage" in category_lower or "dressing" in category_lower or "mask" in category_lower or "thermometer" in category_lower:
                    uom_name = "PACK"
                elif "gloves" in category_lower:
                    uom_name = "PACK"
                elif "cotton" in category_lower or "gauze" in category_lower:
                    uom_name = "PACK"
                else:
                    uom_name = "PACK"  # Default for other categories
            else:
                uom_name = "PACK"  # Default if no category
        
        if uom_name:
            try:
                uom = Uom.objects.filter(name__iexact=uom_name).first()
                if uom:
                    return uom
            except:
                pass
        
        # Fallback: try to use selling_uom or base_uom
        if medicine_data.get("selling_uom"):
            return medicine_data.get("selling_uom")
        if medicine_data.get("base_uom"):
            return medicine_data.get("base_uom")
        
        return None

    def validate(self, attrs):
        medicine = attrs.get("medicine") or {}
        batch = attrs.get("batch") or {}
        quantity = Decimal(str(batch.get("quantity", 0)))
        
        # Infer quantity_uom from stock_unit if not provided
        quantity_uom = batch.get("quantity_uom")
        if not quantity_uom:
            stock_unit = batch.get("stock_unit")
            # Category is already validated and converted to ID by validate_category
            category_id = medicine.get("category")
            quantity_uom = self._infer_quantity_uom(stock_unit, category_id, medicine)
            if quantity_uom:
                batch["quantity_uom"] = quantity_uom
            elif stock_unit:
                # If we can't infer, try to use units_per_pack to determine
                # This is a fallback - quantity_uom will be inferred in convert_quantity_to_base
                pass
        
        # Debug: Log packaging fields to verify they're being received
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"AddMedicine: quantity={quantity}, stock_unit={batch.get('stock_unit')}, "
                   f"tablets_per_strip={medicine.get('tablets_per_strip')}, "
                   f"strips_per_box={medicine.get('strips_per_box')}, "
                   f"capsules_per_strip={medicine.get('capsules_per_strip')}, "
                   f"category={medicine.get('category')}, "
                   f"quantity_uom={quantity_uom}")
        
        qty_base, factor = convert_quantity_to_base(
            quantity=quantity,
            base_uom=medicine.get("base_uom"),
            selling_uom=medicine.get("selling_uom"),
            quantity_uom=quantity_uom,
            units_per_pack=medicine.get("units_per_pack"),
            stock_unit=batch.get("stock_unit"),  # Pass stock_unit for inference
            tablets_per_strip=medicine.get("tablets_per_strip"),
            capsules_per_strip=medicine.get("capsules_per_strip"),
            strips_per_box=medicine.get("strips_per_box"),
            ml_per_bottle=medicine.get("ml_per_bottle"),
            bottles_per_box=medicine.get("bottles_per_box"),
            ml_per_vial=medicine.get("ml_per_vial"),
            grams_per_tube=medicine.get("grams_per_tube"),
            tubes_per_box=medicine.get("tubes_per_box"),
            vials_per_box=medicine.get("vials_per_box"),
            grams_per_sachet=medicine.get("grams_per_sachet"),
            sachets_per_box=medicine.get("sachets_per_box"),
            grams_per_bar=medicine.get("grams_per_bar"),
            bars_per_box=medicine.get("bars_per_box"),
            pieces_per_pack=medicine.get("pieces_per_pack"),
            packs_per_box=medicine.get("packs_per_box"),
            pairs_per_pack=medicine.get("pairs_per_pack"),
            grams_per_pack=medicine.get("grams_per_pack"),
            doses_per_inhaler=medicine.get("doses_per_inhaler"),
            inhalers_per_box=medicine.get("inhalers_per_box"),
        )
        
        logger.info(f"AddMedicine: Calculated qty_base={qty_base}, factor={factor}")
        batch["quantity_base"] = qty_base
        batch["conversion_factor"] = qty_base
        batch["unit_factor"] = factor
        attrs["batch"] = batch
        attrs["medicine"] = medicine
        return attrs


class UpdateMedicineRequestSerializer(AddMedicineRequestSerializer):
    batch = MedicineBatchUpdateSerializer()


class MedicineResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField(allow_null=True, required=False)
    name = serializers.CharField()
    generic_name = serializers.CharField(required=False, allow_blank=True)
    strength = serializers.CharField(required=False, allow_blank=True)
    category = MasterRefSerializer()
    form = MasterRefSerializer()
    base_uom = MasterRefSerializer()
    selling_uom = MasterRefSerializer()
    rack_location = MasterRefSerializer()
    gst_percent = serializers.CharField()
    description = serializers.CharField()
    storage_instructions = serializers.CharField()
    # Tablet/Capsule packaging
    tablets_per_strip = serializers.IntegerField(required=False, allow_null=True)
    capsules_per_strip = serializers.IntegerField(required=False, allow_null=True)
    strips_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Liquid packaging
    ml_per_bottle = serializers.CharField(required=False, allow_null=True)
    bottles_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Injection/Vial packaging
    ml_per_vial = serializers.CharField(required=False, allow_null=True)
    vials_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Ointment/Cream/Gel packaging
    grams_per_tube = serializers.CharField(required=False, allow_null=True)
    tubes_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Inhaler packaging
    doses_per_inhaler = serializers.IntegerField(required=False, allow_null=True)
    inhalers_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Powder/Sachet packaging
    grams_per_sachet = serializers.CharField(required=False, allow_null=True)
    sachets_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Soap/Bar packaging
    grams_per_bar = serializers.CharField(required=False, allow_null=True)
    bars_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Pack/Generic packaging
    pieces_per_pack = serializers.IntegerField(required=False, allow_null=True)
    packs_per_box = serializers.IntegerField(required=False, allow_null=True)
    # Gloves/Pairs packaging
    pairs_per_pack = serializers.IntegerField(required=False, allow_null=True)
    # Cotton/Gauze packaging
    grams_per_pack = serializers.CharField(required=False, allow_null=True)
    units_per_pack = serializers.CharField()
    mrp = serializers.CharField()
    status = serializers.CharField()


class MedicineBatchResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    batch_number = serializers.CharField()
    status = serializers.CharField()
    mfg_date = serializers.DateField(allow_null=True)
    expiry_date = serializers.DateField(allow_null=True)
    quantity = serializers.CharField()
    quantity_uom = MasterRefSerializer()
    base_quantity = serializers.CharField()
    purchase_price = serializers.CharField()
    purchase_price_per_base = serializers.CharField()
    current_stock_base = serializers.CharField()


class InventorySummarySerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    movement_id = serializers.IntegerField(allow_null=True)
    stock_status = serializers.CharField()
    stock_on_hand_base = serializers.CharField()


class AddMedicineResponseSerializer(serializers.Serializer):
    medicine = MedicineResponseSerializer()
    batch = MedicineBatchResponseSerializer()
    inventory = InventorySummarySerializer()

