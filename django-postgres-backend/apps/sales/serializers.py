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
        read_only_fields = ("line_total", "tax_amount", "sale_invoice")

    def validate(self, data):
        prod = data.get("product")
        batch = data.get("batch_lot")

        if prod and batch and batch.product_id != prod.id:
            raise serializers.ValidationError("Batch does not belong to product")

        qty = data.get("qty_base")
        if qty is not None and Decimal(qty) <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero")

        return data



class SalesPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesPayment
        fields = "__all__"
        read_only_fields = ("id", "received_at", "received_by")

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Payment amount must be > 0")
        return v



class SalesInvoiceSerializer(serializers.ModelSerializer):
    # Nested serializers
    lines = SalesLineSerializer(many=True)
    payments = SalesPaymentSerializer(many=True, read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

    # Computed / read-only fields
    total_paid = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )
    outstanding = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )
    payment_status = serializers.CharField(read_only=True)
    round_off_amount = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )

    class Meta:
        model = SalesInvoice
        fields = "__all__"
        read_only_fields = (
            "gross_total",
            "discount_total",
            "tax_total",
            "round_off_amount",
            "net_total",
            "total_paid",
            "outstanding",
            "payment_status",
            "posted_at",
            "posted_by",
            "created_at",
            "updated_at",
            "invoice_no",  # auto-generated
        )

    def validate(self, data):
        lines = data.get("lines") or []
        if not lines:
            raise serializers.ValidationError("Invoice must have at least one line item.")
        return data

    def _compute_totals_and_create_lines(self, invoice, lines):
        gross = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        net = Decimal("0")

        for ln in lines:
            qty = Decimal(ln["qty_base"])
            rate = Decimal(ln["rate_per_base"])
            disc_amt = Decimal(ln.get("discount_amount", 0))
            taxable = (qty * rate) - disc_amt

            tax_amt = (
                taxable * Decimal(ln.get("tax_percent", 0)) / Decimal("100")
            ).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            line_total = (taxable + tax_amt).quantize(
                AMOUNT_QUANT, rounding=ROUND_HALF_UP
            )

            ln["tax_amount"] = tax_amt
            ln["line_total"] = line_total

            SalesLine.objects.create(sale_invoice=invoice, **ln)

            gross += qty * rate
            discount_total += disc_amt
            tax_total += tax_amt
            net += line_total

        net_rounded = net.quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)
        round_off = (net_rounded - net).quantize(CURRENCY_QUANT, rounding=ROUND_HALF_UP)

        return (
            gross.quantize(CURRENCY_QUANT),
            discount_total.quantize(CURRENCY_QUANT),
            tax_total.quantize(CURRENCY_QUANT),
            net_rounded,
            round_off,
        )

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        invoice = SalesInvoice.objects.create(**validated_data)

        gross, disc, tax, net, round_off = self._compute_totals_and_create_lines(
            invoice, lines
        )

        invoice.gross_total = gross
        invoice.discount_total = disc
        invoice.tax_total = tax
        invoice.net_total = net
        invoice.round_off_amount = round_off
        invoice.outstanding = net  # initially full outstanding
        invoice.total_paid = Decimal("0.00")
        invoice.save()
        return invoice

    def update(self, instance, validated_data):
        if instance.status != SalesInvoice.Status.DRAFT:
            raise serializers.ValidationError("Only DRAFT invoices can be edited.")

        lines = validated_data.pop("lines", None)

        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if lines is not None:
            instance.lines.all().delete()
            gross, disc, tax, net, round_off = self._compute_totals_and_create_lines(
                instance, lines
            )
            instance.gross_total = gross
            instance.discount_total = disc
            instance.tax_total = tax
            instance.net_total = net
            instance.round_off_amount = round_off
            instance.save()

        return instance
