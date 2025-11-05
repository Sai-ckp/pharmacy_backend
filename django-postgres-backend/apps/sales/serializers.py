from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import SalesInvoice, SalesLine, SalesPayment
from apps.catalog.models import Product, BatchLot
from apps.customers.models import Customer

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")


class SalesLineSerializer(serializers.ModelSerializer):
    qty_packs = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, write_only=True)

    class Meta:
        model = SalesLine
        fields = "__all__"
        read_only_fields = ("hsn_code", "batch_no", "expiry_date", "product_name", "pack_text", "mrp", "ptr", "pts", "line_total")

    def validate_qty_base(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty_base must be > 0")
        return v

    def validate_sold_uom(self, v):
        if v not in {"BASE", "PACK"}:
            raise serializers.ValidationError("sold_uom must be BASE or PACK")
        return v

    def validate(self, data):
        prod = data.get("product")
        batch = data.get("batch_lot")

        if prod and batch and batch.product_id != prod.id:
            raise serializers.ValidationError("batch_lot does not belong to product")

        # compute qty_base if qty_packs provided
        qty_packs = data.pop("qty_packs", None)
        if qty_packs is not None:
            units = getattr(prod, "units_per_pack", None)
            if not units or units == 0:
                raise serializers.ValidationError("product.units_per_pack missing; cannot compute qty_base")
            data["qty_base"] = (Decimal(qty_packs) * Decimal(units)).quantize(AMOUNT_QUANT)

        # populate snapshots
        if prod:
            data.setdefault("product_name", prod.name)
            data.setdefault("hsn_code", getattr(prod, "hsn", ""))
            data.setdefault("pack_text", f"{getattr(prod,'units_per_pack','')} {getattr(prod,'pack_unit','')}")
            data.setdefault("mrp", getattr(prod, "mrp", None))
        if batch:
            data.setdefault("batch_no", batch.batch_no)
            data.setdefault("expiry_date", batch.expiry_date)

        return data


class SalesInvoiceSerializer(serializers.ModelSerializer):
    lines = SalesLineSerializer(many=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

    class Meta:
        model = SalesInvoice
        fields = "__all__"
        read_only_fields = ("gross_total", "tax_total", "net_total", "created_at", "updated_at", "posted_at", "posted_by")

    def validate(self, data):
        lines = data.get("lines") or []
        if not lines:
            raise serializers.ValidationError("Invoice must include at least one line")

        # If any line requires prescription, ensure header/prescription present
        if any(l.get("requires_prescription") for l in lines):
            if not (data.get("prescription") or data.get("doctor_name") or data.get("patient_name")):
                raise serializers.ValidationError("Prescribing doctor/patient or prescription required for controlled lines")
        return data

    def _compute_totals_and_create_lines(self, invoice, lines):
        gross = Decimal("0")
        tax_total = Decimal("0")
        discount_total = Decimal("0")
        net = Decimal("0")
        for ln in lines:
            qty = Decimal(ln["qty_base"])
            rate = Decimal(ln["rate_per_base"])
            disc_amt = Decimal(ln.get("discount_amount") or 0)
            taxable = (qty * rate) - disc_amt
            tax_amt = Decimal(ln.get("tax_amount") or (taxable * Decimal(ln.get("tax_percent", 0)) / Decimal("100")))
            tax_amt = tax_amt.quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            line_total = (taxable + tax_amt).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)

            ln["tax_amount"] = tax_amt
            ln["line_total"] = line_total
            SalesLine.objects.create(sale_invoice=invoice, **ln)

            gross += (qty * rate)
            discount_total += disc_amt
            tax_total += tax_amt
            net += line_total

        return gross.quantize(CURRENCY_QUANT), discount_total.quantize(CURRENCY_QUANT), tax_total.quantize(CURRENCY_QUANT), net.quantize(CURRENCY_QUANT)

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        invoice = SalesInvoice.objects.create(**validated_data)
        gross, discount_total, tax_total, net = self._compute_totals_and_create_lines(invoice, lines)
        invoice.gross_total = gross
        invoice.discount_total = discount_total
        invoice.tax_total = tax_total
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


class SalesPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesPayment
        fields = "__all__"

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("amount must be > 0")
        return v
