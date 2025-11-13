# apps/sales/views.py
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction

from .models import SalesInvoice, SalesPayment
from .serializers import SalesInvoiceSerializer, SalesPaymentSerializer
from . import services
from apps.settingsx.services import next_doc_number

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
