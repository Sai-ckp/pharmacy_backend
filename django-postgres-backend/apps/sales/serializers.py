from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import SalesInvoice, SalesLine, SalesPayment
from apps.catalog.models import Product
from apps.inventory.models import BatchLot
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
        if data.get("qty_base") and data["qty_base"] <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero")
        return data


class SalesInvoiceSerializer(serializers.ModelSerializer):
    lines = SalesLineSerializer(many=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

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
        )

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
