from rest_framework import serializers
from .models import (
    SettingKV,
    BusinessProfile,
    DocCounter,
    PaymentMethod,
    PaymentTerm,
    NotificationSettings,
    TaxBillingSettings,
)
from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Name already exists"


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettingKV
        fields = "__all__"


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = "__all__"


class DocCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocCounter
        fields = "__all__"


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        method_type = attrs.get("method_type") or getattr(self.instance, "method_type", None) or PaymentMethod.MethodType.OTHER
        if method_type not in dict(PaymentMethod.MethodType.choices):
            raise serializers.ValidationError({"method_type": "Invalid method type."})
        qs = PaymentMethod.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        attrs["method_type"] = method_type
        return attrs


class PaymentTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTerm
        fields = "__all__"

    def validate(self, attrs):
        name = (attrs.get("name") or self.instance and self.instance.name or "").strip()
        if not name:
            raise serializers.ValidationError({"name": "This field is required."})
        days = attrs.get("days", 0)
        if days is not None and int(days) < 0:
            raise serializers.ValidationError({"days": "Must be >= 0"})
        desc = attrs.get("description")
        if desc and len(desc) > 512:
            raise serializers.ValidationError({"description": "Max 512 chars."})
        qs = PaymentTerm.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise Conflict()
        attrs["name"] = name
        return attrs


class NotificationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSettings
        fields = "__all__"


class TaxBillingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxBillingSettings
        fields = "__all__"

    def validate(self, attrs):
        for fld in ("gst_rate", "cgst_rate", "sgst_rate"):
            val = attrs.get(fld)
            if val is not None and val < 0:
                raise serializers.ValidationError({fld: "Must be >= 0"})
        return attrs

