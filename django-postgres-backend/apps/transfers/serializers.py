from rest_framework import serializers
from .models import TransferVoucher, TransferLine

class TransferLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransferLine
        fields = "__all__"

    def validate_qty_base(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty_base must be > 0")
        return v


class TransferVoucherSerializer(serializers.ModelSerializer):
    lines = TransferLineSerializer(many=True)

    class Meta:
        model = TransferVoucher
        fields = "__all__"
        read_only_fields = ("posted_at", "posted_by", "created_at")

    def validate(self, data):
        if data["from_location"] == data["to_location"]:
            raise serializers.ValidationError("from_location and to_location cannot be same")
        if not data.get("lines"):
            raise serializers.ValidationError("transfer must include lines")
        return data

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        voucher = TransferVoucher.objects.create(**validated_data)
        for l in lines:
            TransferLine.objects.create(voucher=voucher, **l)
        return voucher

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for l in lines:
                TransferLine.objects.create(voucher=instance, **l)
        return instance
