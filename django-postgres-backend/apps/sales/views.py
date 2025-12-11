# apps/sales/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter, OpenApiExample
from django.db.models import Sum, F
from datetime import date

from .models import SalesInvoice, SalesPayment
from .serializers import SalesInvoiceSerializer, SalesPaymentSerializer
from . import services
from apps.settingsx.services import next_doc_number
from apps.settingsx.models import TaxBillingSettings, DocCounter
from apps.inventory.models import InventoryMovement
from apps.catalog.models import Product, BatchLot
from core.permissions import HasActiveSystemLicense


LICENSED_PERMISSIONS = [IsAuthenticated, HasActiveSystemLicense]

class SalesInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SalesInvoice.objects.all().select_related("customer", "location", "posted_by", "created_by", "payment_type").prefetch_related("payments")
    serializer_class = SalesInvoiceSerializer
    permission_classes = LICENSED_PERMISSIONS
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "customer", "location"]
    search_fields = ["invoice_no", "customer__name"]

    def perform_create(self, serializer):
        # create with created_by then ensure invoice_no is generated if not provided
        invoice = serializer.save(created_by=self.request.user)
        if not invoice.invoice_no:
            # Ensure DocCounter exists and aligns with TaxBillingSettings
            settings = TaxBillingSettings.objects.first()
            prefix = (settings.invoice_prefix or "INV-") if settings else "INV-"
            start_num = (settings.invoice_start or 1) if settings else 1
            padding = 4
            DocCounter.objects.get_or_create(
                document_type="INVOICE",
                defaults={"prefix": prefix, "next_number": start_num, "padding_int": padding},
            )
            invoice.invoice_no = next_doc_number("INVOICE", prefix=prefix, padding=padding)
            invoice.save(update_fields=["invoice_no"])

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.status == SalesInvoice.Status.POSTED:
            return Response({"detail": "Cannot delete a POSTED invoice. Cancel instead."}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="post")
    def post_invoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            # service handles locking and idempotency
            result = services.post_invoice(actor=request.user, invoice_id=invoice.id)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_invoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            result = services.cancel_invoice(actor=request.user, invoice_id=invoice.id)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        tags=["Sales"],
        summary="Complete payment (post invoice if needed and record payment)",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("Complete", value={"mode": "CASH", "amount": "auto"})],
    )
    @action(detail=True, methods=["post"], url_path="complete-payment")
    def complete_payment(self, request, pk=None):
        invoice = self.get_object()
        with transaction.atomic():
            # Ensure it is posted
            if invoice.status == SalesInvoice.Status.DRAFT:
                services.post_invoice(actor=request.user, invoice_id=invoice.id)
                invoice.refresh_from_db()
            amount = request.data.get("amount")
            from decimal import Decimal
            if amount in (None, "auto", ""):
                amount = invoice.net_total
            else:
                amount = Decimal(str(amount))
            mode = request.data.get("mode") or "CASH"
            pay_ser = SalesPaymentSerializer(data={
                "sale_invoice": invoice.id,
                "amount": amount,
                "mode": mode,
            })
            pay_ser.is_valid(raise_exception=True)
            pay = pay_ser.save(received_by=request.user)
            # Refresh invoice to get updated payment status
            invoice.refresh_from_db()
        return Response({
            "invoice_no": invoice.invoice_no,
            "payment_id": pay.id,
            "total_paid": str(invoice.total_paid),
            "outstanding": str(invoice.outstanding),
            "payment_status": invoice.payment_status,
        })

    @extend_schema(
        tags=["Sales"],
        summary="Printable HTML for invoice",
        responses={200: OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"], url_path="print", permission_classes=LICENSED_PERMISSIONS)
    def print_view(self, request, pk=None):
        inv = self.get_object()
        html = self._render_invoice_html(inv)
        return Response(html, content_type="text/html")

    @extend_schema(
        tags=["Sales"],
        summary="Download HTML invoice (attachment)",
        responses={200: OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"], url_path="download", permission_classes=LICENSED_PERMISSIONS)
    def download(self, request, pk=None):
        inv = self.get_object()
        from django.http import HttpResponse
        html = self._render_invoice_html(inv)
        resp = HttpResponse(html, content_type="text/html")
        filename = (inv.invoice_no or f"invoice-{inv.id}") + ".html"
        resp["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        return resp

    @extend_schema(
        tags=["Sales"],
        summary="Download PDF invoice",
        responses={200: OpenApiTypes.BINARY, 501: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="pdf", permission_classes=LICENSED_PERMISSIONS)
    def pdf(self, request, pk=None):
        inv = self.get_object()
        html = self._render_invoice_html(inv)
        pdf_bytes = None
        # Try WeasyPrint first
        try:
            from weasyprint import HTML  # type: ignore
            pdf_bytes = HTML(string=html).write_pdf()
        except Exception:
            pdf_bytes = None
        if pdf_bytes is None:
            # Fallback to xhtml2pdf
            try:
                from xhtml2pdf import pisa  # type: ignore
                import io
                out = io.BytesIO()
                pisa.CreatePDF(io.StringIO(html), dest=out)
                pdf_bytes = out.getvalue()
            except Exception:
                pdf_bytes = None
        if not pdf_bytes:
            return Response({"ok": False, "code": "PDF_ENGINE_MISSING"}, status=501)
        from django.http import HttpResponse
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = (inv.invoice_no or f"invoice-{inv.id}") + ".pdf"
        resp["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        return resp

    @extend_schema(
        tags=["Sales"],
        summary="Export invoices list as CSV",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("customer", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("location", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.STR},
    )
    @action(detail=False, methods=["get"], url_path="export", permission_classes=LICENSED_PERMISSIONS)
    def export_csv(self, request):
        qs = self.filter_queryset(self.get_queryset())
        import csv
        from django.http import HttpResponse
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = "attachment; filename=\"invoices.csv\""
        writer = csv.writer(resp)
        writer.writerow(["invoice_no", "invoice_date", "customer", "total_items", "net_total", "payment_status"])
        for inv in qs:
            writer.writerow([
                inv.invoice_no or inv.id,
                inv.invoice_date.strftime("%Y-%m-%d %H:%M"),
                getattr(inv.customer, "name", "-"),
                inv.lines.count(),
                inv.net_total,
                inv.payment_status,
            ])
        return resp

    def _render_invoice_html(self, inv: SalesInvoice) -> str:
        lines = inv.lines.select_related("product", "batch_lot").all()
        customer = getattr(inv, "customer", None)
        company = {
            "name": "",
            "address": "",
            "phone": "",
            "email": "",
            "gst": "",
        }
        try:
            from apps.settingsx.models import BusinessProfile
            bp = BusinessProfile.objects.first()
            if bp:
                company = {
                    "name": bp.business_name,
                    "address": bp.address,
                    "phone": bp.phone,
                    "email": bp.email,
                    "gst": bp.gst_number,
                }
        except Exception:
            pass
        # Customer details for Bill To section
        cust_name = getattr(customer, "name", "-") if customer else "-"
        cust_phone = getattr(customer, "phone", "") if customer else ""
        cust_email = getattr(customer, "email", "") if customer else ""
        cust_addr_parts = []
        if getattr(customer, "billing_address", None):
            cust_addr_parts.append(customer.billing_address)
        city_parts = []
        if getattr(customer, "city", None):
            city_parts.append(customer.city)
        if getattr(customer, "state_code", None):
            city_parts.append(customer.state_code)
        city_line = ", ".join(city_parts)
        if city_line:
            cust_addr_parts.append(city_line)
        if getattr(customer, "pincode", None):
            cust_addr_parts.append(customer.pincode)
        cust_address = ", ".join([p for p in cust_addr_parts if p])

        # Payment information
        last_payment = inv.payments.order_by("-received_at").first()
        payment_mode = last_payment.mode if last_payment else "-"
        served_by = "-"
        try:
            user = getattr(inv, "created_by", None)
            if user:
                served_by = getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "-")
        except Exception:
            pass

        rows = "".join([
            f"<tr><td>{i+1}</td><td>{ln.product.name}</td><td>{ln.batch_lot.batch_no}</td><td>{ln.qty_base}</td><td>{ln.rate_per_base}</td><td>{ln.line_total}</td></tr>"
            for i, ln in enumerate(lines)
        ])
        html = f"""
        <html><head><meta charset='utf-8'><title>Invoice {inv.invoice_no or inv.id}</title>
        <style>body{{font-family:Arial,Helvetica,sans-serif}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:8px}}</style>
        </head><body>
        <h2>Invoice #{inv.invoice_no or inv.id}</h2>
        <p>Date: {inv.invoice_date.strftime('%d-%m-%Y %H:%M')}</p>
        <h3>{company['name']}</h3>
        <p>{company['address']}<br/>Phone: {company['phone']} Email: {company['email']}<br/>GST: {company['gst']}</p>
        <h4>Bill To:</h4>
        <p>
            {cust_name}<br/>
            {cust_phone if cust_phone else ""}{("<br/>" if cust_phone and cust_email else "") if cust_email else ""}{cust_email if cust_email else ""}{("<br/>" if (cust_phone or cust_email) and cust_address else "") if cust_address else ""}{cust_address if cust_address else ""}
        </p>
        <table><thead><tr><th>#</th><th>Medicine Name</th><th>Batch</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p>Subtotal: {inv.gross_total} &nbsp; GST: {inv.tax_total} &nbsp; Total: {inv.net_total}</p>
        <p>Payment Method: {payment_mode} &nbsp; Payment Status: {inv.payment_status}</p>
        <p>Served By: {served_by}</p>
        <p>Thank you for choosing our pharmacy</p>
        </body></html>
        """
        return html


class SalesPaymentViewSet(viewsets.ModelViewSet):
    queryset = SalesPayment.objects.all().select_related("sale_invoice", "received_by")
    serializer_class = SalesPaymentSerializer
    permission_classes = LICENSED_PERMISSIONS

    def perform_create(self, serializer):
        # atomic to ensure payment saved and invoice totals updated together
        with transaction.atomic():
            payment = serializer.save(received_by=self.request.user)
            # recompute totals on invoice
            services._update_payment_status(payment.sale_invoice)


class BillingStatsView(APIView):
    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Sales"],
        summary="Billing dashboard summary (posted invoices)",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        if from_str:
            qs = qs.filter(invoice_date__date__gte=from_str)
        if to_str:
            qs = qs.filter(invoice_date__date__lte=to_str)
        total_bills = qs.count()
        total_revenue = qs.aggregate(s=Sum("net_total")).get("s") or 0
        # items sold = sum of all line quantities for posted invoices in range
        lines = (
            SalesInvoice.objects.filter(id__in=qs.values_list("id", flat=True))
            .values_list("lines__qty_base", flat=True)
        )
        total_items = sum([float(x or 0) for x in lines])
        return Response({"total_bills": total_bills, "total_products_sold": total_items, "total_revenue": float(total_revenue)})


class MedicinesSuggestView(APIView):
    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Sales"],
        summary="Suggest medicines with current stock and MRP",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        q = request.query_params.get("q")
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        prod_qs = Product.objects.filter(is_active=True)
        if q:
            prod_qs = prod_qs.filter(
                filters.Q(name__icontains=q) | filters.Q(generic_name__icontains=q) | filters.Q(code__icontains=q)
            )
        # Aggregate stock per product
        stock_rows = (
            InventoryMovement.objects.filter(location_id=location_id)
            .values("batch_lot__product_id")
            .annotate(stock=Sum("qty_change_base"))
        )
        stock_map = {r["batch_lot__product_id"]: r["stock"] for r in stock_rows}
        products = prod_qs.values("id", "code", "name", "generic_name", "manufacturer", "mrp", "gst_percent")[:50]
        out = []
        for p in products:
            out.append({
                "product_id": p["id"],
                "code": p["code"],
                "name": p["name"],
                "generic_name": p["generic_name"],
                "manufacturer": p["manufacturer"],
                "mrp": str(p["mrp"]),
                "gst_percent": str(p["gst_percent"]),
                "stock": float(stock_map.get(p["id"], 0) or 0),
            })
        return Response(out)


class InvoiceQuoteView(APIView):
    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Sales"],
        summary="Stateless invoice quote calculation",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("Quote", value={
            "lines": [
                {"product_id": 1, "qty_base": "10.000", "rate_per_base": "2.50", "tax_percent": "12"}
            ]
        })],
    )
    def post(self, request):
        from decimal import Decimal, ROUND_HALF_UP
        lines = request.data.get("lines") or []
        if not isinstance(lines, list) or not lines:
            return Response({"detail": "lines required"}, status=status.HTTP_400_BAD_REQUEST)
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        detail = []
        for ln in lines:
            qty = Decimal(str(ln.get("qty_base") or "0"))
            rate = Decimal(str(ln.get("rate_per_base") or "0"))
            pct = Decimal(str(ln.get("tax_percent") or "0"))
            gross = qty * rate
            tax = (gross * pct / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += gross
            tax_total += tax
            detail.append({"gross": str(gross.quantize(Decimal("0.01"))), "tax": str(tax), "pct": str(pct)})
        net = (subtotal + tax_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Response({
            "subtotal": str(subtotal.quantize(Decimal("0.01"))),
            "tax_total": str(tax_total.quantize(Decimal("0.01"))),
            "net_total": str(net),
            "lines": detail,
        })
