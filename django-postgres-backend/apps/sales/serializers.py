from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import SalesInvoice, SalesLine, SalesPayment
from apps.catalog.models import Product, BatchLot
from apps.customers.models import Customer
from apps.settingsx.models import PaymentMethod
from apps.customers.serializers import CustomerSerializer
from django.utils import timezone

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")


class SalesLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)


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
    customer_detail = CustomerSerializer(source="customer", read_only=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )

    # expose payment_type as writable FK and a read-only nested detail
    payment_type = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.all(),
        required=False,
        allow_null=True,
        write_only=False
    )
    payment_type_detail = serializers.SerializerMethodField(read_only=True)

    def get_payment_type_detail(self, obj):
        if obj.payment_type:
            return {"id": obj.payment_type.id, "name": str(obj.payment_type)}
        return None

    # Optional inline customer fields for new customers created from bill screen
    customer_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    customer_billing_address = serializers.CharField(write_only=True, required=False, allow_blank=True)
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
        # NOTE: your original code used customer_id and then created Customer
        customer = validated_data.get("customer_id")
        if customer:
            return customer
        # Pop inline fields (they are not model fields)
        name = validated_data.pop("customer_name", None)
        phone = validated_data.pop("customer_phone", None)
        email = validated_data.pop("customer_email", None)
        billing_address = validated_data.pop("customer_billing_address", None)
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
            billing_address=billing_address or None,
            shipping_address=billing_address or None,
            city=city or None,
            state_code=state_code or None,
            pincode=pincode or None,
            type=Customer.Type.RETAIL,
            is_active=True,
        )

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])

        # Extract payment details from request
        # Note: incoming keys from the client should be "payment_method" and "amount_paid"
        # payment_method is the ID used for SalesPayment creation.
        payment_method = validated_data.pop("payment_method", None)
        amount_paid = validated_data.pop("amount_paid", None)

        # If client passed "payment_type" (invoice-level FK), consume it here
        payment_type = validated_data.pop("payment_type", None)

        # Attach or create customer if needed
        customer = self._get_or_create_customer_from_inline(validated_data)
        if customer is not None:
            validated_data["customer_id"] = customer.id

        # Create invoice (initially draft)
        invoice = SalesInvoice.objects.create(**validated_data)

        # Compute line totals & create SalesLine rows
        gross, disc, tax, net, round_off = self._compute_totals_and_create_lines(
            invoice, lines
        )

        invoice.gross_total = gross
        invoice.discount_total = disc
        invoice.tax_total = tax
        invoice.net_total = net
        invoice.round_off_amount = round_off

        # Default before payments
        total_paid = Decimal("0.00")

        # -------------------- PAYMENT HANDLING --------------------
        # If client provided payment_method and amount_paid -> create SalesPayment and update invoice
        if payment_method and amount_paid:
            # create payment record
            SalesPayment.objects.create(
                invoice=invoice,
                payment_method_id=payment_method,
                amount=Decimal(amount_paid),
                received_by=self.context["request"].user
            )
            total_paid = Decimal(amount_paid)

            # set invoice's payment_type to the payment_method used (if not provided separately)
            try:
                invoice.payment_type_id = payment_type.id if hasattr(payment_type, "id") else payment_type or payment_method
            except Exception:
                invoice.payment_type_id = payment_method

            # Mark invoice as posted and set posted metadata
            invoice.status = SalesInvoice.Status.POSTED
            invoice.posted_at = timezone.now()
            invoice.posted_by = self.context["request"].user

        # If client only passed payment_type (invoice-level) but no immediate payment, attach it
        elif payment_type:
            try:
                invoice.payment_type = payment_type
            except Exception:
                # If payment_type is provided as primary key:
                invoice.payment_type_id = payment_type

        # Update payment status based on totals
        invoice.total_paid = total_paid
        # outstanding = net - total_paid
        invoice.outstanding = (net - total_paid).quantize(CURRENCY_QUANT)

        # Set payment_status enum
        if total_paid == Decimal("0.00"):
            invoice.payment_status = SalesInvoice.PaymentStatus.CREDIT
        elif total_paid >= net:
            invoice.payment_status = SalesInvoice.PaymentStatus.PAID
        else:
            invoice.payment_status = SalesInvoice.PaymentStatus.PARTIAL

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
        validated_data.pop("customer_billing_address", None)
        validated_data.pop("customer_city", None)
        validated_data.pop("customer_state_code", None)
        validated_data.pop("customer_pincode", None)

        # allow updating payment_type if provided
        if "payment_type" in validated_data:
            pt = validated_data.pop("payment_type")
            try:
                instance.payment_type = pt
            except Exception:
                instance.payment_type_id = pt

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

            # Recompute outstanding based on existing payments
            paid_sum = instance.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
            instance.total_paid = paid_sum
            instance.outstanding = (net - paid_sum).quantize(CURRENCY_QUANT)

            # Update payment status
            if paid_sum == Decimal("0.00"):
                instance.payment_status = SalesInvoice.PaymentStatus.CREDIT
            elif paid_sum >= net:
                instance.payment_status = SalesInvoice.PaymentStatus.PAID
                instance.status = SalesInvoice.Status.POSTED
                instance.posted_at = timezone.now()
                instance.posted_by = self.context["request"].user
            else:
                instance.payment_status = SalesInvoice.PaymentStatus.PARTIAL

            instance.save()

        return instance