from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import (
    Vendor, Purchase, PurchasePayment, PurchaseDocument, VendorReturn,
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
)
from .serializers import (
    VendorSerializer, PurchaseSerializer, PurchasePaymentSerializer,
    PurchaseDocumentSerializer, VendorReturnSerializer,
    PurchaseOrderSerializer, GoodsReceiptSerializer,
)
from .services import post_purchase, post_vendor_return
from core.utils.doc_numbers import next_doc_number
from apps.catalog.models import BatchLot
from apps.inventory.services import write_movement


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


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all().prefetch_related("lines")
    serializer_class = PurchaseOrderSerializer

    def perform_create(self, serializer):
        po_number = next_doc_number('PO')
        serializer.save(po_number=po_number, created_by=self.request.user if self.request.user.is_authenticated else None)


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all().prefetch_related("lines")
    serializer_class = GoodsReceiptSerializer

    @action(detail=True, methods=["post"], url_path="post")
    @transaction.atomic
    def post_grn(self, request, pk=None):
        grn = get_object_or_404(GoodsReceipt, pk=pk)
        for ln in grn.lines.select_related("product"):
            batch, _ = BatchLot.objects.get_or_create(
                product=ln.product, batch_no=ln.batch_no,
                defaults={"mfg_date": ln.mfg_date, "expiry_date": ln.expiry_date, "status": BatchLot.Status.ACTIVE}
            )
            if ln.mfg_date and not batch.mfg_date:
                batch.mfg_date = ln.mfg_date
            if ln.expiry_date and not batch.expiry_date:
                batch.expiry_date = ln.expiry_date
            batch.save()
            qty_base = (ln.qty_base_received or 0) - (ln.qty_base_damaged or 0)
            write_movement(
                location_id=grn.location_id,
                batch_lot_id=batch.id,
                qty_change_base=qty_base,
                reason="PURCHASE",
                ref_doc_type="GRN",
                ref_doc_id=grn.id,
            )
        # Update PO status naive check
        po = grn.po
        total_ordered = sum(l.qty_packs_ordered for l in po.lines.all()) or 0
        total_received = sum(gl.qty_packs_received for gl in GoodsReceiptLine.objects.filter(po_line__po=po)) or 0
        if total_ordered and total_received >= total_ordered:
            po.status = PurchaseOrder.Status.COMPLETED
        else:
            po.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
        po.save(update_fields=["status"])
        grn.status = GoodsReceipt.Status.POSTED
        grn.save(update_fields=["status"])
        return Response({"posted": True})

