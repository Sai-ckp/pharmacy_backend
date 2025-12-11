from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.db import transaction
from .models import SalesInvoice, SalesLine, SalesPayment
from apps.catalog.models import Product, BatchLot
from apps.customers.models import Customer
from apps.settingsx.models import PaymentMethod, TaxBillingSettings
from apps.customers.serializers import CustomerSerializer
from django.utils import timezone
from apps.inventory.services import stock_on_hand

AMOUNT_QUANT = Decimal("0.0001")
CURRENCY_QUANT = Decimal("0.01")


class SalesLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    hsn_code = serializers.SerializerMethodField(read_only=True)
    expiry_date = serializers.SerializerMethodField(read_only=True)
    batch_no = serializers.SerializerMethodField(read_only=True)
    gst_percent = serializers.SerializerMethodField(read_only=True)

    def get_hsn_code(self, obj):
        """Get HSN code from the product"""
        if obj.product and hasattr(obj.product, 'hsn') and obj.product.hsn:
            return obj.product.hsn
        return None

    def get_expiry_date(self, obj):
        """Get expiry date from batch_lot"""
        if obj.batch_lot and obj.batch_lot.expiry_date:
            return obj.batch_lot.expiry_date.strftime("%d/%m/%Y")
        return None

    def get_batch_no(self, obj):
        """Get batch number from batch_lot"""
        if obj.batch_lot and obj.batch_lot.batch_no:
            return obj.batch_lot.batch_no
        return None

    def get_gst_percent(self, obj):
        """Alias for tax_percent to match frontend expectations"""
        return obj.tax_percent

    class Meta:
        model = SalesLine
        fields = "__all__"
        read_only_fields = ("line_total", "tax_amount", "sale_invoice")
        extra_kwargs = {
            "sold_uom": {"required": False},
            "batch_lot": {"required": False},
        }
       
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
        # Round to 4 decimal places to ensure it fits within max_digits=14, decimal_places=4
        # This ensures no more than 14 total digits (10 before decimal + 4 after)
        if isinstance(v, Decimal):
            v = v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
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
    
    # Doctor name field
    doctor_name = serializers.CharField(required=False, allow_blank=True)

    # Computed / read-only fields
    # Note: We use a method field to return customer name from linked customer
    # The write_only customer_name above is for creating new customers
    customer_name_display = serializers.SerializerMethodField(read_only=True)
    total_paid = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )
    outstanding = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )
    payment_status = serializers.CharField(read_only=True)
    payment_method_display = serializers.SerializerMethodField(read_only=True)
    round_off_amount = serializers.DecimalField(
        max_digits=14, decimal_places=4, read_only=True
    )

    def get_customer_name_display(self, obj):
        """Return customer name for easy access in frontend"""
        if obj.customer:
            return obj.customer.name
        return None

    def get_payment_method_display(self, obj):
        """Return payment method from the latest payment, or payment_type, or payment_status"""
        # Force refresh to get latest payments (especially if just created in same request)
        try:
            obj.refresh_from_db(fields=[])
        except Exception:
            pass
        
        # Get the latest payment's mode - ensure we get the most recent one
        payments = obj.payments.all().order_by('-received_at')
        latest_payment = payments.first() if payments.exists() else None
        
        if latest_payment and latest_payment.mode:
            # Return the payment mode (CASH, UPI, etc.) - ensure uppercase and trimmed
            return str(latest_payment.mode).upper().strip()
        
        # Fallback to payment_type if available
        if obj.payment_type and hasattr(obj.payment_type, 'type'):
            return str(obj.payment_type.type).upper().strip()
        
        # Fallback to payment_status (PAID, PARTIAL, CREDIT)
        if obj.payment_status:
            return str(obj.payment_status).upper().strip()
        
        return "CREDIT"

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
        settings = TaxBillingSettings.objects.first()
        default_pct = Decimal(str(settings.gst_rate)) if settings and settings.gst_rate is not None else Decimal("0")
        calc_method = (settings.calc_method or "INCLUSIVE").upper() if settings else "INCLUSIVE"

        gross = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        net = Decimal("0")

        for ln in lines:
            qty = Decimal(ln["qty_base"])
            rate = Decimal(ln["rate_per_base"])
            disc_amt = Decimal(ln.get("discount_amount", 0))
            pct = Decimal(ln.get("tax_percent") or default_pct)
            # Inclusive/exclusive handling
            line_gross = qty * rate
            taxable = (line_gross - disc_amt)
            if calc_method == "INCLUSIVE" and pct > 0:
                taxable = (taxable / (Decimal("1") + pct / Decimal("100"))).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            tax_amt = (
                taxable * pct / Decimal("100")
            ).quantize(AMOUNT_QUANT, rounding=ROUND_HALF_UP)
            line_total = (taxable + tax_amt).quantize(
                AMOUNT_QUANT, rounding=ROUND_HALF_UP
            )

            ln["tax_percent"] = pct
            ln["tax_amount"] = tax_amt
            ln["line_total"] = line_total

            SalesLine.objects.create(sale_invoice=invoice, **ln)

            gross += line_gross
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

    def _allocate_fefo(self, product: Product, ln: dict, location_id: int | None):
        qty_needed = Decimal(ln.get("qty_base") or 0)
        if qty_needed <= 0 or not location_id:
            return [ln]
        batches = (
            BatchLot.objects.filter(product=product)
            .order_by("expiry_date", "id")
        )
        allocations = []
        remaining = qty_needed
        for batch in batches:
            available = stock_on_hand(location_id, batch.id)
            if available <= 0:
                continue
            take = min(available, remaining)
            if take <= 0:
                continue
            new_ln = dict(ln)
            new_ln["batch_lot"] = batch
            new_ln["qty_base"] = take
            allocations.append(new_ln)
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            raise serializers.ValidationError(
                {"detail": f"Insufficient stock for {product.name}. Need {qty_needed}, available {qty_needed-remaining}."}
            )
        return allocations

    @transaction.atomic
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

        # FEFO allocation if batch not supplied
        allocated_lines = []
        location_id = validated_data.get("location_id") or validated_data.get("location").id if validated_data.get("location") else None
        for ln in lines:
            ln.setdefault("sold_uom", "BASE")
            batch = ln.get("batch_lot")
            product = ln.get("product")
            if not batch and product:
                allocated_lines.extend(self._allocate_fefo(product, ln, location_id))
            else:
                allocated_lines.append(ln)

        # Compute line totals & create SalesLine rows
        gross, disc, tax, net, round_off = self._compute_totals_and_create_lines(
            invoice, allocated_lines
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
            # Ensure invoice and lines are fully saved before posting
            invoice.save()
            # Refresh to ensure all relationships are loaded
            invoice.refresh_from_db()
            
            # Call post_invoice service to properly calculate totals and mark as posted
            # This ensures totals are correctly calculated, inventory is deducted, and invoice is posted
            from apps.sales import services
            try:
                # Post invoice - this deducts stock and marks as POSTED
                result = services.post_invoice(actor=self.context["request"].user, invoice_id=invoice.id)
                # Refresh to get latest state
                invoice.refresh_from_db()
                
                # Verify invoice was actually posted (not skipped due to idempotency or error)
                if invoice.status != SalesInvoice.Status.POSTED:
                    raise serializers.ValidationError(
                        f"Invoice was not posted. Current status: {invoice.status}. "
                        "This may indicate insufficient stock or other error."
                    )
            except ValidationError as ve:
                # Re-raise validation errors as-is
                raise serializers.ValidationError(str(ve))
            except Exception as e:
                # If post_invoice fails for any reason, re-raise the error
                raise serializers.ValidationError(f"Failed to post invoice: {str(e)}")
            
            # Only create payment if invoice was successfully posted
            # create payment record - ensure mode is uppercase string (e.g., "CASH", "UPI")
            payment_mode = str(payment_method).upper().strip()
            payment = SalesPayment.objects.create(
                sale_invoice=invoice,
                mode=payment_mode,
                amount=Decimal(amount_paid),
                received_by=self.context["request"].user
            )
            
            # Explicitly update payment status (don't rely on save hook alone)
            services._update_payment_status(invoice)
            # Refresh to ensure payment is visible in relationships
            invoice.refresh_from_db()
            # Also refresh payment to ensure it's committed
            payment.refresh_from_db()

            # set invoice's payment_type to the payment_method used (if not provided separately)
            try:
                invoice.payment_type_id = payment_type.id if hasattr(payment_type, "id") else payment_type or payment_method
            except Exception:
                # If payment_type is a string (like "CASH", "UPI"), try to find PaymentMethod object
                # Otherwise, just set the string value (it will be ignored if it's not a valid FK)
                try:
                    from apps.settingsx.models import PaymentMethod
                    pm = PaymentMethod.objects.filter(type=payment_method).first()
                    if pm:
                        invoice.payment_type = pm
                    else:
                        # If no PaymentMethod found, leave payment_type as None
                        # The payment mode is stored in SalesPayment.mode anyway
                        pass
                except Exception:
                    pass
            invoice.save(update_fields=["payment_type"])

        # If client only passed payment_type (invoice-level) but no immediate payment, attach it
        elif payment_type:
            try:
                invoice.payment_type = payment_type
            except Exception:
                # If payment_type is provided as primary key:
                invoice.payment_type_id = payment_type
            invoice.save(update_fields=["payment_type"])

        # If no payment was made, set default status and save
        if not (payment_method and amount_paid):
            invoice.total_paid = Decimal("0.00")
            invoice.outstanding = net
            invoice.payment_status = SalesInvoice.PaymentStatus.CREDIT
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
