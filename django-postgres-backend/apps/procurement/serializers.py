from rest_framework import serializers
from django.db import transaction
from decimal import Decimal
from apps.catalog.models import Product
from .services_pricing import compute_po_line_totals
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
        extra_kwargs = {
            "po": {"required": False},
            "expected_unit_cost": {"required": False},
        }


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, required=False)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"
        extra_kwargs = {
            "po_number": {"read_only": True},
            "gross_total": {"read_only": True},
            "tax_total": {"read_only": True},
            "net_total": {"read_only": True},
        }

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        # ignore any incoming totals from FE
        validated_data.pop("gross_total", None)
        validated_data.pop("tax_total", None)
        validated_data.pop("net_total", None)

        po = PurchaseOrder.objects.create(**validated_data)
        gross_total = Decimal("0.00")
        tax_total = Decimal("0.00")
        for line in lines:
            product = Product.objects.get(id=line["product"].id if hasattr(line.get("product"), "id") else line["product"])
            qty = Decimal(line.get("qty_packs_ordered") or 0)
            # if frontend didn't send unit cost (UI hides price field), derive sensible default
            raw_cost = line.get("expected_unit_cost")
            if raw_cost in (None, "", 0, "0"):
                from .models import GoodsReceiptLine, GoodsReceipt
                vendor = validated_data.get("vendor")
                cost = None
                if vendor is not None:
                    # latest GRN for this vendor+product
                    gl = (
                        GoodsReceiptLine.objects.filter(
                            grn__po__vendor=vendor,
                            grn__status=GoodsReceipt.Status.POSTED,
                            product_id=product.id,
                        )
                        .order_by("-grn__received_at")
                        .first()
                    )
                    if gl:
                        cost = gl.unit_cost
                # fallback to product.mrp
                if cost is None:
                    cost = product.mrp
                line["expected_unit_cost"] = cost
            else:
                cost = Decimal(raw_cost)
            gst_override = line.get("gst_percent_override")
            parts = compute_po_line_totals(
                qty_packs=qty,
                unit_cost_pack=cost,
                product_gst_percent=Decimal(product.gst_percent or 0),
                gst_override=Decimal(gst_override) if gst_override is not None else None,
            )
            gross_total += parts["gross"]
            tax_total += parts["tax"]
            PurchaseOrderLine.objects.create(po=po, **line)
        po.gross_total = gross_total
        po.tax_total = tax_total
        po.net_total = (gross_total + tax_total).quantize(Decimal("0.01"))
        po.save(update_fields=["gross_total", "tax_total", "net_total"])
        return po

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        validated_data.pop("gross_total", None)
        validated_data.pop("tax_total", None)
        validated_data.pop("net_total", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        # Recompute only if lines provided; leave lines intact otherwise
        if lines is not None:
            gross_total = Decimal("0.00")
            tax_total = Decimal("0.00")
            # naive: replace all lines
            PurchaseOrderLine.objects.filter(po=instance).delete()
            for line in lines:
                product = Product.objects.get(id=line["product"].id if hasattr(line.get("product"), "id") else line["product"])
                qty = Decimal(line.get("qty_packs_ordered") or 0)
                raw_cost = line.get("expected_unit_cost")
                if raw_cost in (None, "", 0, "0"):
                    from .models import GoodsReceiptLine, GoodsReceipt
                    vendor = instance.vendor
                    cost = None
                    if vendor is not None:
                        gl = (
                            GoodsReceiptLine.objects.filter(
                                grn__po__vendor=vendor,
                                grn__status=GoodsReceipt.Status.POSTED,
                                product_id=product.id,
                            )
                            .order_by("-grn__received_at")
                            .first()
                        )
                        if gl:
                            cost = gl.unit_cost
                    if cost is None:
                        cost = product.mrp
                    line["expected_unit_cost"] = cost
                else:
                    cost = Decimal(raw_cost)
                gst_override = line.get("gst_percent_override")
                parts = compute_po_line_totals(
                    qty_packs=qty,
                    unit_cost_pack=cost,
                    product_gst_percent=Decimal(product.gst_percent or 0),
                    gst_override=Decimal(gst_override) if gst_override is not None else None,
                )
                gross_total += parts["gross"]
                tax_total += parts["tax"]
                PurchaseOrderLine.objects.create(po=instance, **line)
            instance.gross_total = gross_total
            instance.tax_total = tax_total
            instance.net_total = (gross_total + tax_total).quantize(Decimal("0.01"))
            instance.save(update_fields=["gross_total", "tax_total", "net_total"])
        return instance


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

