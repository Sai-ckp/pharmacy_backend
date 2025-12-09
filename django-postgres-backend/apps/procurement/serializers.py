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
    category = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = PurchaseOrderLine
        fields = "__all__"
        extra_kwargs = {
            "po": {"required": False},
            "expected_unit_cost": {"required": False},
            "product": {"required": False, "allow_null": True},
            "medicine_form": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        product = attrs.get("product")
        requested_name = (attrs.get("requested_name") or "").strip()
        if not product and not requested_name:
            raise serializers.ValidationError("Either product or requested_name must be provided.")
        attrs["requested_name"] = requested_name
        return attrs


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
        gross_total, tax_total = self._save_lines(po, lines, validated_data.get("vendor"))
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
            PurchaseOrderLine.objects.filter(po=instance).delete()
            gross_total, tax_total = self._save_lines(instance, lines, instance.vendor)
            instance.gross_total = gross_total
            instance.tax_total = tax_total
            instance.net_total = (gross_total + tax_total).quantize(Decimal("0.01"))
            instance.save(update_fields=["gross_total", "tax_total", "net_total"])
        return instance

    def _save_lines(self, po, lines, vendor):
        gross_total = Decimal("0.00")
        tax_total = Decimal("0.00")
        vendor_obj = vendor
        for raw in lines:
            line = dict(raw)
            product = line.get("product")
            if product and not isinstance(product, Product):
                product = Product.objects.filter(id=product).first()
            line["product"] = product
            # PO does not create catalog product.
            # If product exists → use its name.
            if product and not line.get("requested_name"):
                line["requested_name"] = product.name
            # If no product → requested_name is already validated
            qty = Decimal(str(line.get("qty_packs_ordered") or "0"))
            raw_cost = line.get("expected_unit_cost")
            cost = Decimal(str(raw_cost or "0"))
            if raw_cost in (None, "", 0, "0"):
                cost = self._derive_unit_cost(product, vendor_obj)
                line["expected_unit_cost"] = cost
            gst_override = line.get("gst_percent_override")
            product_gst = Decimal(product.gst_percent or 0) if product else Decimal("0")
            parts = compute_po_line_totals(
                qty_packs=qty,
                unit_cost_pack=cost,
                product_gst_percent=product_gst,
                gst_override=Decimal(gst_override) if gst_override is not None else None,
            )
            gross_total += parts["gross"]
            tax_total += parts["tax"]
            PurchaseOrderLine.objects.create(po=po, **line)
        return gross_total, tax_total

    def _derive_unit_cost(self, product, vendor):
        if not product:
            return Decimal("0.00")
        from .models import GoodsReceiptLine, GoodsReceipt

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
            cost = product.mrp or Decimal("0.00")
        return Decimal(cost)


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    new_product = serializers.DictField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = GoodsReceiptLine
        fields = "__all__"
        extra_kwargs = {
            "product": {"required": False, "allow_null": True},
            "qty_base_received": {"required": False, "allow_null": True},
            "grn": {"required": False},
        }

    def validate(self, attrs):
        new_product = attrs.pop("new_product", None)
        product = attrs.get("product")
        if not product and not new_product:
            raise serializers.ValidationError("Either product or new_product must be supplied.")
        if new_product:
            product_id = new_product.get("product_id") or new_product.get("id")
            if not product_id:
                # Required fields (medicine_form is optional, will be set to None if not provided)
                required = ["name", "base_unit", "pack_unit", "units_per_pack", "mrp"]
                missing = [field for field in required if not new_product.get(field)]
                if missing:
                    raise serializers.ValidationError(
                        {"new_product": f"Missing fields: {', '.join(missing)}"}
                    )
            attrs["new_product_payload"] = new_product
        return attrs


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

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for line in lines:
                GoodsReceiptLine.objects.create(grn=instance, **line)
        return instance

