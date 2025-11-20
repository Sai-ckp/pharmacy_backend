from rest_framework import serializers
from .models import ProductCategory, Product, BatchLot, MedicineForm, Uom, VendorProductCode
from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Name already exists"


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        qs = ProductCategory.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_name = serializers.CharField(source="preferred_vendor.name", read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": True},
            "category": {"required": True},
            "preferred_vendor": {"required": True},
            "pack_unit": {"required": True},

            # All these should NOT be required
            "mrp": {"required": False},
            "generic_name": {"required": False},
            "dosage_strength": {"required": False},
            "hsn": {"required": False},
            "schedule": {"required": False},
            "manufacturer": {"required": False},
            "base_unit": {"required": False},
            "units_per_pack": {"required": False},
            "base_unit_step": {"required": False},
            "gst_percent": {"required": False},
            "reorder_level": {"required": False},
            "description": {"required": False},
            "storage_instructions": {"required": False},
            "code": {"required": False},
        }

    def create(self, validated_data):

        # Auto-generate product code
        if "code" not in validated_data or not validated_data["code"]:
            last = Product.objects.order_by("-id").first()
            next_id = (last.id + 1) if last else 1
            validated_data["code"] = f"PRD-{next_id:05d}"

        # Default values (prevent validation errors)
        validated_data.setdefault("mrp", 0)
        validated_data.setdefault("generic_name", "")
        validated_data.setdefault("dosage_strength", "")
        validated_data.setdefault("hsn", "")
        validated_data.setdefault("schedule", "OTC")
        validated_data.setdefault("manufacturer", "")
        validated_data.setdefault("base_unit", "unit")
        validated_data.setdefault("units_per_pack", 1)
        validated_data.setdefault("base_unit_step", 1)
        validated_data.setdefault("gst_percent", 0)
        validated_data.setdefault("reorder_level", 0)
        validated_data.setdefault("description", "")
        validated_data.setdefault("storage_instructions", "")

        return super().create(validated_data)



class BatchLotSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchLot
        fields = "__all__"


class MedicineFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineForm
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        qs = MedicineForm.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        return attrs


class UomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Uom
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        qs = Uom.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        return attrs


class VendorProductCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorProductCode
        fields = "__all__"

    def validate(self, attrs):
        vendor = attrs.get("vendor") or (self.instance and self.instance.vendor)
        code = (attrs.get("vendor_code") or (self.instance and self.instance.vendor_code) or "").strip()
        if not vendor or not code:
            raise serializers.ValidationError({"vendor_code": "vendor and vendor_code required"})
        qs = VendorProductCode.objects.filter(vendor=vendor, vendor_code__iexact=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["vendor_code"] = code
        return attrs

