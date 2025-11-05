from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import SalesInvoice, SalesPayment
from .serializers import SalesInvoiceSerializer, SalesPaymentSerializer
from . import services

class SalesInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SalesInvoice.objects.all().select_related("customer", "location")
    serializer_class = SalesInvoiceSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["invoice_no", "customer__name"]

    @action(detail=True, methods=["post"], url_path="post")
    def post_invoice(self, request, pk=None):
        invoice = self.get_object()
        try:
            result = services.post_invoice(invoice.id, actor=request.user)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class SalesPaymentViewSet(viewsets.ModelViewSet):
    queryset = SalesPayment.objects.all().select_related("sale_invoice", "received_by")
    serializer_class = SalesPaymentSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)
