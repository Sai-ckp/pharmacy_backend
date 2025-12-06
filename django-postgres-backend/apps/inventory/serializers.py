from decimal import Decimal
from copy import deepcopy

from django.utils import timezone
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.catalog.models import ProductCategory, Product, MedicineForm, Uom
from .models import InventoryMovement, RackLocation
from .services import (
    convert_quantity_to_base,
    BOX_NAMES,
    BOTTLE_NAMES,
    GM_BASE_NAMES,
    ML_BASE_NAMES,
    STRIP_NAMES,
    TAB_BASE_NAMES,
    TUBE_NAMES,
    VIAL_BASE_NAMES,
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
    category = serializers.PrimaryKeyRelatedField(queryset=ProductCategory.objects.all())
    form = serializers.PrimaryKeyRelatedField(queryset=MedicineForm.objects.all(), source="medicine_form")
    strength = serializers.CharField(max_length=64, required=False, allow_blank=True)
    base_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all())
    selling_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all())
    rack_location = serializers.PrimaryKeyRelatedField(queryset=RackLocation.objects.all())
    tablets_per_strip = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    strips_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    ml_per_bottle = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    bottles_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    vials_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    ml_per_vial = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    grams_per_tube = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    tubes_per_box = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    gst_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    mrp = serializers.DecimalField(max_digits=14, decimal_places=2)
    units_per_pack = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)

    def validate_id(self, value):
        if value and not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError("Invalid medicine id.")
        return value

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
        strips_per_box = attrs.get("strips_per_box")
        selling_uom = attrs.get("selling_uom")
        base_uom = attrs.get("base_uom")
        ml_per_bottle = attrs.get("ml_per_bottle")
        bottles_per_box = attrs.get("bottles_per_box")
        grams_per_tube = attrs.get("grams_per_tube")
        tubes_per_box = attrs.get("tubes_per_box")
        vials_per_box = attrs.get("vials_per_box")
        if units_per_pack is not None:
            units_per_pack = Decimal(str(units_per_pack))
        inferred = self._infer_units_per_pack(
            provided=units_per_pack,
            selling_uom=selling_uom,
            base_uom=base_uom,
            tablets_per_strip=tablets_per_strip,
            strips_per_box=strips_per_box,
            ml_per_bottle=ml_per_bottle,
            bottles_per_box=bottles_per_box,
            grams_per_tube=grams_per_tube,
            tubes_per_box=tubes_per_box,
            vials_per_box=vials_per_box,
        )
        if inferred is None:
            raise serializers.ValidationError({"units_per_pack": "Unable to determine units_per_pack for the selected UOMs."})
        attrs["units_per_pack"] = inferred

        gst_percent = attrs.get("gst_percent")
        attrs["gst_percent"] = Decimal(str(gst_percent or 0))
        attrs["mrp"] = Decimal(str(attrs.get("mrp")))
        self._enforce_packaging_rules(attrs)
        return attrs

    @staticmethod
    def _infer_units_per_pack(
        *,
        provided: Decimal | None,
        selling_uom: Uom,
        base_uom: Uom,
        tablets_per_strip: int | None,
        strips_per_box: int | None,
        ml_per_bottle: Decimal | None = None,
        bottles_per_box: int | None = None,
        grams_per_tube: Decimal | None = None,
        tubes_per_box: int | None = None,
        vials_per_box: int | None = None,
    ) -> Decimal | None:
        if provided is not None:
            if provided <= 0:
                raise serializers.ValidationError({"units_per_pack": "Must be greater than zero."})
            return provided
        if selling_uom and base_uom and selling_uom.id == base_uom.id:
            return Decimal("1.000")
        selling_name = (selling_uom.name or "").strip().upper() if selling_uom else ""
        base_name = (base_uom.name or "").strip().upper() if base_uom else ""
        if selling_name in STRIP_NAMES and base_name in TAB_BASE_NAMES:
            if not tablets_per_strip:
                raise serializers.ValidationError({"tablets_per_strip": "tablets_per_strip is required for STRIP quantities."})
            return Decimal(tablets_per_strip)
        if selling_name in BOX_NAMES and base_name in TAB_BASE_NAMES:
            if not tablets_per_strip:
                raise serializers.ValidationError({"tablets_per_strip": "tablets_per_strip is required for BOX quantities."})
            if not strips_per_box:
                raise serializers.ValidationError({"strips_per_box": "strips_per_box is required for BOX quantities."})
            return Decimal(tablets_per_strip) * Decimal(strips_per_box)
        if selling_name in BOTTLE_NAMES and base_name in ML_BASE_NAMES:
            if not ml_per_bottle:
                raise serializers.ValidationError({"ml_per_bottle": "ml_per_bottle is required for bottle quantities."})
            return Decimal(ml_per_bottle)
        if selling_name in BOX_NAMES and base_name in ML_BASE_NAMES:
            if not ml_per_bottle:
                raise serializers.ValidationError({"ml_per_bottle": "ml_per_bottle is required for box quantities."})
            if not bottles_per_box:
                raise serializers.ValidationError({"bottles_per_box": "bottles_per_box is required for box quantities."})
            return Decimal(ml_per_bottle) * Decimal(bottles_per_box)
        if selling_name in TUBE_NAMES and base_name in GM_BASE_NAMES:
            if not grams_per_tube:
                raise serializers.ValidationError({"grams_per_tube": "grams_per_tube is required for tube quantities."})
            return Decimal(grams_per_tube)
        if selling_name in BOX_NAMES and base_name in GM_BASE_NAMES:
            if not grams_per_tube:
                raise serializers.ValidationError({"grams_per_tube": "grams_per_tube is required for box quantities."})
            if not tubes_per_box:
                raise serializers.ValidationError({"tubes_per_box": "tubes_per_box is required for box quantities."})
            return Decimal(grams_per_tube) * Decimal(tubes_per_box)
        if selling_name in BOX_NAMES and base_name in VIAL_BASE_NAMES:
            if not vials_per_box:
                raise serializers.ValidationError({"vials_per_box": "vials_per_box is required for box quantities."})
            return Decimal(vials_per_box)
        return None

    def _enforce_packaging_rules(self, attrs: dict) -> None:
        base_uom = attrs.get("base_uom")
        form = attrs.get("medicine_form")
        if not base_uom or not form:
            return
        base_name = (base_uom.name or "").strip().upper()
        form_name = (form.name or "").strip().upper()

        def require_positive(value, field, message):
            if value in (None, ""):
                raise serializers.ValidationError({field: message})
            if isinstance(value, (int, float, Decimal)):
                if Decimal(str(value)) <= 0:
                    raise serializers.ValidationError({field: message})

        if base_name in TAB_BASE_NAMES and form_name in {"TABLET", "CAPSULE"}:
            require_positive(attrs.get("tablets_per_strip"), "tablets_per_strip", "Tablets per strip is required for tablet/capsule forms.")
            require_positive(attrs.get("strips_per_box"), "strips_per_box", "Strips per box is required for tablet/capsule forms.")
        elif base_name in ML_BASE_NAMES and form_name in {"SYRUP", "SUSPENSION", "DROPS"}:
            require_positive(attrs.get("ml_per_bottle"), "ml_per_bottle", "ML per bottle is required for liquid forms.")
            require_positive(attrs.get("bottles_per_box"), "bottles_per_box", "Bottles per box is required for liquid forms.")
        elif base_name in VIAL_BASE_NAMES and form_name in {"INJECTION", "VIAL", "AMPOULE"}:
            require_positive(attrs.get("vials_per_box"), "vials_per_box", "Vials per box is required for injection/vial forms.")
        elif base_name in GM_BASE_NAMES and form_name in {"OINTMENT", "CREAM", "GEL"}:
            require_positive(attrs.get("grams_per_tube"), "grams_per_tube", "Grams per tube is required for ointment/cream/gel forms.")
            require_positive(attrs.get("tubes_per_box"), "tubes_per_box", "Tubes per box is required for ointment/cream/gel forms.")


class MedicineBatchInputSerializer(serializers.Serializer):
    batch_number = serializers.CharField(max_length=64)
    mfg_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField()
    quantity = serializers.IntegerField(min_value=0)
    quantity_uom = serializers.PrimaryKeyRelatedField(queryset=Uom.objects.all())
    purchase_price = serializers.DecimalField(max_digits=14, decimal_places=2)

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
        attrs["purchase_price"] = Decimal(str(attrs.get("purchase_price")))
        attrs["quantity"] = int(attrs.get("quantity"))
        return attrs


class MedicineBatchUpdateSerializer(MedicineBatchInputSerializer):
    id = serializers.IntegerField()


class AddMedicineRequestSerializer(serializers.Serializer):
    location_id = serializers.IntegerField(required=False)
    medicine = MedicinePayloadSerializer()
    batch = MedicineBatchInputSerializer()

    packaging_fields = (
        "tablets_per_strip",
        "strips_per_box",
        "ml_per_bottle",
        "bottles_per_box",
        "vials_per_box",
        "ml_per_vial",
        "grams_per_tube",
        "tubes_per_box",
    )

    def to_internal_value(self, data):
        data = deepcopy(data)
        medicine = data.get("medicine") or {}
        packaging = medicine.pop("packaging", None) or {}
        for field in self.packaging_fields:
            if field in packaging and medicine.get(field) in (None, "", 0):
                medicine[field] = packaging[field]
        if "mrp_per_selling_uom" in medicine and medicine.get("mrp") in (None, "", 0):
            medicine["mrp"] = medicine.pop("mrp_per_selling_uom")
        data["medicine"] = medicine

        batch = data.get("batch") or {}
        if "opening_stock_selling_uom" in batch and batch.get("quantity") in (None, ""):
            batch["quantity"] = batch.pop("opening_stock_selling_uom")
        if "purchase_price_per_selling_uom" in batch and batch.get("purchase_price") in (None, ""):
            batch["purchase_price"] = batch.pop("purchase_price_per_selling_uom")
        data["batch"] = batch
        return super().to_internal_value(data)

    def validate(self, attrs):
        medicine = attrs.get("medicine") or {}
        batch = attrs.get("batch") or {}
        if not batch.get("quantity_uom") and medicine.get("selling_uom"):
            batch["quantity_uom"] = medicine.get("selling_uom")
        quantity = Decimal(str(batch.get("quantity", 0)))
        qty_base, factor = convert_quantity_to_base(
            quantity=quantity,
            base_uom=medicine.get("base_uom"),
            selling_uom=medicine.get("selling_uom"),
            quantity_uom=batch.get("quantity_uom"),
            units_per_pack=medicine.get("units_per_pack"),
            tablets_per_strip=medicine.get("tablets_per_strip"),
            strips_per_box=medicine.get("strips_per_box"),
            ml_per_bottle=medicine.get("ml_per_bottle"),
            bottles_per_box=medicine.get("bottles_per_box"),
            grams_per_tube=medicine.get("grams_per_tube"),
            tubes_per_box=medicine.get("tubes_per_box"),
            vials_per_box=medicine.get("vials_per_box"),
        )
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
    tablets_per_strip = serializers.IntegerField(required=False, allow_null=True)
    strips_per_box = serializers.IntegerField(required=False, allow_null=True)
    mrp = serializers.CharField()
    status = serializers.CharField()
    packaging = serializers.DictField(child=serializers.CharField(allow_null=True), required=False)
    mrp_per_selling_uom = serializers.CharField()


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
    opening_stock_selling_uom = serializers.CharField()
    purchase_price_per_selling_uom = serializers.CharField()


class InventorySummarySerializer(serializers.Serializer):
    location_id = serializers.IntegerField()
    movement_id = serializers.IntegerField(allow_null=True)
    stock_status = serializers.CharField()
    stock_on_hand_base = serializers.CharField()


class AddMedicineResponseSerializer(serializers.Serializer):
    medicine = MedicineResponseSerializer()
    batch = MedicineBatchResponseSerializer()
    inventory = InventorySummarySerializer()

