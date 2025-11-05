from rest_framework import serializers
from .models import (
    Vendor, Purchase, PurchaseLine, PurchasePayment, PurchaseDocument, VendorReturn,
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
)


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


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderLine
        fields = "__all__"


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        po = PurchaseOrder.objects.create(**validated_data)
        for line in lines:
            PurchaseOrderLine.objects.create(po=po, **line)
        return po


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodsReceiptLine
        fields = "__all__"


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptLineSerializer(many=True, required=False)

    class Meta:
        model = GoodsReceipt
        fields = "__all__"

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        grn = GoodsReceipt.objects.create(**validated_data)
        for line in lines:
            GoodsReceiptLine.objects.create(grn=grn, **line)
        return grn

