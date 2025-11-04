from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404

from .models import Vendor, Purchase, PurchasePayment, PurchaseDocument, VendorReturn
from .serializers import (
    VendorSerializer, PurchaseSerializer, PurchasePaymentSerializer,
    PurchaseDocumentSerializer, VendorReturnSerializer
)
from .services import post_purchase, post_vendor_return


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer


class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = Purchase.objects.all().prefetch_related("lines")
    serializer_class = PurchaseSerializer

    @action(detail=True, methods=["post"], url_path="post")
    def post_purchase(self, request, pk=None):
        p = get_object_or_404(Purchase, pk=pk)
        post_purchase(p.id, actor=request.user if request.user.is_authenticated else None)
        return Response({"posted": True})


class PurchasePaymentViewSet(viewsets.ModelViewSet):
    queryset = PurchasePayment.objects.all()
    serializer_class = PurchasePaymentSerializer


class PurchaseDocumentViewSet(viewsets.ModelViewSet):
    queryset = PurchaseDocument.objects.all()
    serializer_class = PurchaseDocumentSerializer


class VendorReturnViewSet(viewsets.ModelViewSet):
    queryset = VendorReturn.objects.all()
    serializer_class = VendorReturnSerializer

    @action(detail=True, methods=["post"], url_path="post")
    def post_return(self, request, pk=None):
        vr = get_object_or_404(VendorReturn, pk=pk)
        post_vendor_return(vr.id, actor=request.user if request.user.is_authenticated else None)
        return Response({"posted": True})

