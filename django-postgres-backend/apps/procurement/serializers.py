from rest_framework import serializers
from .models import Vendor, Purchase, PurchaseLine, PurchasePayment, PurchaseDocument, VendorReturn


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = "__all__"


class PurchaseLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseLine
        fields = "__all__"


class PurchaseSerializer(serializers.ModelSerializer):
    lines = PurchaseLineSerializer(many=True, required=False)

    class Meta:
        model = Purchase
        fields = "__all__"

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        purchase = Purchase.objects.create(**validated_data)
        for line in lines:
            PurchaseLine.objects.create(purchase=purchase, **line)
        return purchase


class PurchasePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchasePayment
        fields = "__all__"


class PurchaseDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseDocument
        fields = "__all__"


class VendorReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorReturn
        fields = "__all__"

