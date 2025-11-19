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
    # Existing customer (by id)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    # Optional inline customer fields for new customers created from bill screen
    customer_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    customer_city = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_state_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_pincode = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
            "created_by",
            "invoice_no",  # auto-generated
        )

    def validate(self, data):
        lines = data.get("lines") or []
        if not lines:
            raise serializers.ValidationError("Invoice must have at least one line item.")
        # Ensure we have either an existing customer or enough data to create one
        customer = data.get("customer")
        if not customer:
            name = self.initial_data.get("customer_name") if self.initial_data else None
            phone = self.initial_data.get("customer_phone") if self.initial_data else None
            email = self.initial_data.get("customer_email") if self.initial_data else None
            city = self.initial_data.get("customer_city") if self.initial_data else None
            if not name or not phone or not city:
                raise serializers.ValidationError(
                    "Either an existing customer must be provided or customer_name, "
                    "customer_phone and customer_city must be sent."
                )
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

    def _get_or_create_customer_from_inline(self, validated_data):
        customer = validated_data.get("customer")
        if customer:
            return customer
        # Pop inline fields (they are not model fields)
        name = validated_data.pop("customer_name", None)
        phone = validated_data.pop("customer_phone", None)
        email = validated_data.pop("customer_email", None)
        city = validated_data.pop("customer_city", None)
        state_code = validated_data.pop("customer_state_code", None)
        pincode = validated_data.pop("customer_pincode", None)
        if not name and not phone and not city:
            # Nothing to do; leave customer as None (caller validation already enforced requirements)
            return None
        # If phone matches an existing customer, reuse it
        existing = None
        if phone:
            existing = Customer.objects.filter(phone=phone).first()
        if existing:
            return existing
        # Generate a simple unique customer code
        last_id = Customer.objects.order_by("-id").values_list("id", flat=True).first() or 0
        base = last_id + 1
        code = f"CUST-{base:05d}"
        # Ensure uniqueness in case of gaps
        while Customer.objects.filter(code=code).exists():
            base += 1
            code = f"CUST-{base:05d}"
        return Customer.objects.create(
            name=name or "Walk-in Customer",
            code=code,
            phone=phone or None,
            email=email or None,
            city=city or None,
            state_code=state_code or None,
            pincode=pincode or None,
            type=Customer.Type.RETAIL,
            is_active=True,
        )

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        # Attach or create customer if needed
        customer = self._get_or_create_customer_from_inline(validated_data)
        if customer is not None:
            validated_data["customer"] = customer
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
        # For updates we do not auto-create customers; ignore inline fields if sent
        validated_data.pop("customer_name", None)
        validated_data.pop("customer_phone", None)
        validated_data.pop("customer_email", None)
        validated_data.pop("customer_city", None)
        validated_data.pop("customer_state_code", None)
        validated_data.pop("customer_pincode", None)

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
