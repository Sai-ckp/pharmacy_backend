from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import SalesInvoice, SalesLine, SalesPayment
from apps.catalog.models import Product, BatchLot
from apps.customers.models import Customer

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")


class SalesLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesLine
        fields = "__all__"
        read_only_fields = ("line_total", "tax_amount")

    def validate(self, data):
        prod = data.get("product")
        batch = data.get("batch_lot")

        if prod and batch and batch.product_id != prod.id:
            raise serializers.ValidationError("Batch does not belong to product")
        if data.get("qty_base") and Decimal(data["qty_base"]) <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero")
        return data


class SalesPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesPayment
        fields = "__all__"
        read_only_fields = ("id", "received_at",)

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("amount must be > 0")
        return v


class SalesInvoiceSerializer(serializers.ModelSerializer):
    lines = SalesLineSerializer(many=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

    # computed/read-only fields
    total_paid = serializers.SerializerMethodField(read_only=True)
    outstanding = serializers.SerializerMethodField(read_only=True)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = SalesInvoice
        fields = "__all__"
        read_only_fields = (
            "gross_total",
            "tax_total",
            "net_total",
            "created_at",
            "updated_at",
            "posted_at",
            "posted_by",
            "total_paid",
            "outstanding",
            "payment_status",
        )

    def get_total_paid(self, obj):
        # sum payments if related_name is payments or sales_payments; adapt if different
        payments = getattr(obj, "payments", None) or getattr(obj, "sales_payments", None) or obj.payments.all()
        total = sum([p.amount for p in payments]) if payments else Decimal("0")
        return Decimal(total).quantize(CURRENCY_QUANT)

    def get_outstanding(self, obj):
        total_paid = self.get_total_paid(obj)
        net_total = obj.net_total or Decimal("0")
        try:
            out = (Decimal(net_total) - Decimal(total_paid)).quantize(CURRENCY_QUANT)
        except Exception:
            out = Decimal("0.00")
        return out

    def validate(self, data):
        lines = data.get("lines") or []
        if not lines:
            raise serializers.ValidationError("Invoice must have at least one line item.")
        return data

    def _compute_totals_and_create_lines(self, invoice, lines):
        gross = Decimal("0")
        tax_total = Decimal("0")
        discount_total = Decimal("0")
        net = Decimal("0")

        for ln in lines:
            qty = Decimal(ln["qty_base"])
            rate = Decimal(ln["rate_per_base"])
            disc_amt = Decimal(ln.get("discount_amount", 0))
            taxable = (qty * rate) - disc_amt
            tax_amt = (taxable * Decimal(ln.get("tax_percent", 0)) / Decimal("100")).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            line_total = (taxable + tax_amt).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            ln["tax_amount"] = tax_amt
            ln["line_total"] = line_total
            SalesLine.objects.create(sale_invoice=invoice, **ln)
            gross += qty * rate
            discount_total += disc_amt
            tax_total += tax_amt
            net += line_total

        return (
            gross.quantize(CURRENCY_QUANT),
            discount_total.quantize(CURRENCY_QUANT),
            tax_total.quantize(CURRENCY_QUANT),
            net.quantize(CURRENCY_QUANT),
        )

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        invoice = SalesInvoice.objects.create(**validated_data)
        gross, disc, tax, net = self._compute_totals_and_create_lines(invoice, lines)
        invoice.gross_total = gross
        invoice.discount_total = disc
        invoice.tax_total = tax
        invoice.net_total = net
        invoice.save()
        return invoice

    def update(self, instance, validated_data):
        if instance.status == SalesInvoice.Status.POSTED:
            raise serializers.ValidationError("Cannot edit posted invoice")
        lines = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            gross, discount_total, tax_total, net = self._compute_totals_and_create_lines(instance, lines)
            instance.gross_total = gross
            instance.discount_total = discount_total
            instance.tax_total = tax_total
            instance.net_total = net
            instance.save()
        return instance
