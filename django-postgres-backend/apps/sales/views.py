# apps/sales/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter, OpenApiExample
from django.db.models import Sum, F
from datetime import date

from .models import SalesInvoice, SalesPayment
from .serializers import SalesInvoiceSerializer, SalesPaymentSerializer
from . import services
from apps.settingsx.services import next_doc_number
from apps.inventory.models import InventoryMovement
from apps.catalog.models import Product, BatchLot

class SalesInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SalesInvoice.objects.all().select_related("customer", "location", "posted_by", "created_by")
    serializer_class = SalesInvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["status", "customer", "location"]
    search_fields = ["invoice_no", "customer__name"]

    def perform_create(self, serializer):
        # create with created_by then ensure invoice_no is generated if not provided
        invoice = serializer.save(created_by=self.request.user)
        if not invoice.invoice_no:
            invoice.invoice_no = next_doc_number("INVOICE", "INV-", 5)
            invoice.save(update_fields=["invoice_no"])

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


class SalesPaymentViewSet(viewsets.ModelViewSet):
    queryset = SalesPayment.objects.all().select_related("sale_invoice", "received_by")
    serializer_class = SalesPaymentSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # atomic to ensure payment saved and invoice totals updated together
        with transaction.atomic():
            payment = serializer.save(received_by=self.request.user)
            # recompute totals on invoice
            services._update_payment_status(payment.sale_invoice)


class BillingStatsView(viewsets.ViewSet, APIView):
    permission_classes = [IsAuthenticated]

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


class MedicinesSuggestView(viewsets.ViewSet, APIView):
    permission_classes = [IsAuthenticated]

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


class InvoiceQuoteView(viewsets.ViewSet, APIView):
    permission_classes = [IsAuthenticated]

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
