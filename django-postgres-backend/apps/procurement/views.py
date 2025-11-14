from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiExample, OpenApiParameter
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db import transaction
from decimal import Decimal

from .models import (
    Vendor, Purchase, PurchasePayment, PurchaseDocument, VendorReturn,
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
)
from .serializers import (
    VendorSerializer, PurchaseSerializer, PurchasePaymentSerializer,
    PurchaseDocumentSerializer, VendorReturnSerializer,
    PurchaseOrderSerializer, GoodsReceiptSerializer,
)
from .services import post_purchase, post_vendor_return, post_goods_receipt
from apps.settingsx.services import next_doc_number
from apps.catalog.models import BatchLot
from apps.inventory.services import write_movement
from .importers_pdf import parse_grn_pdf
from apps.catalog.services_vendor_map import product_by_vendor_code
from apps.governance.services import audit
from django.db.models.functions import TruncMonth
from django.db.models import Sum


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

    @action(detail=True, methods=["get", "post"], url_path="lines")
    def po_lines(self, request, pk=None):
        from .serializers import PurchaseOrderLineSerializer
        if request.method.lower() == 'get':
            lines = PurchaseOrderLine.objects.filter(po_id=pk)
            return Response(PurchaseOrderLineSerializer(lines, many=True).data)
        # POST create a line
        ser = PurchaseOrderLineSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(po_id=pk)
        return Response(ser.data, status=status.HTTP_201_CREATED)


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.all().prefetch_related("lines")
    serializer_class = GoodsReceiptSerializer

    @action(detail=True, methods=["post"], url_path="post")
    @transaction.atomic
    def post_grn(self, request, pk=None):
        post_goods_receipt(int(pk), actor=request.user if request.user.is_authenticated else None)
        return Response({"posted": True})


class GrnImportPdfView(APIView):
    @extend_schema(
        tags=["Procurement"],
        summary="Parse GRN PDF and return preview (OCR fallback)",
        responses={200: OpenApiTypes.OBJECT, 422: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        result = parse_grn_pdf(file)
        return Response(result, status=status.HTTP_200_OK if result.get("ok") else status.HTTP_422_UNPROCESSABLE_ENTITY)


class PoImportCommitView(APIView):
    @extend_schema(
        tags=["Procurement"],
        summary="Create a PO from parsed/imported lines (server computes totals)",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("PO Commit", value={
            "vendor_id": 3, "location_id": 1,
            "lines": [{"vendor_code": "CIP-TAB-500", "qty": 2, "unit_cost": "45.00", "gst_percent": "12"}]
        })]
    )
    @transaction.atomic
    def post(self, request):
        vendor_id = request.data.get("vendor_id") or request.data.get("vendor")
        location_id = request.data.get("location_id") or request.data.get("location")
        lines = request.data.get("lines") or []
        if not vendor_id or not location_id or not isinstance(lines, list) or not lines:
            return Response({"detail": "vendor_id, location_id and lines required"}, status=status.HTTP_400_BAD_REQUEST)

        po_payload = {
            "vendor": vendor_id,
            "location": location_id,
            "order_date": request.data.get("order_date"),
            "expected_date": request.data.get("expected_date"),
            "note": request.data.get("note", ""),
            "lines": [],
        }
        for ln in lines:
            product_id = ln.get("product_id")
            if not product_id:
                vend_code = ln.get("vendor_code") or ln.get("product_code") or ""
                prod = product_by_vendor_code(int(vendor_id), vend_code)
                if not prod:
                    return Response({"detail": f"Unable to resolve product for code '{vend_code}'"}, status=status.HTTP_400_BAD_REQUEST)
                product_id = prod.id
            po_payload["lines"].append({
                "product": product_id,
                "qty_packs_ordered": ln.get("qty") or ln.get("qty_packs") or ln.get("qty_packs_ordered") or 0,
                "expected_unit_cost": ln.get("unit_cost") or ln.get("price") or ln.get("expected_unit_cost") or "0.00",
                "gst_percent_override": ln.get("gst_percent") or ln.get("gst_percent_override"),
            })

        ser = PurchaseOrderSerializer(data=po_payload)
        ser.is_valid(raise_exception=True)
        po = ser.save()
        audit(request.user if request.user.is_authenticated else None, table="procurement_purchaseorder", row_id=po.id, action="IMPORT_COMMIT", before=None, after={"lines": len(po_payload["lines"])})
        return Response(ser.data, status=status.HTTP_201_CREATED)


class GrnImportCommitView(APIView):
    @extend_schema(
        tags=["Procurement"],
        summary="Create DRAFT GRN from parsed/imported lines against a PO",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @transaction.atomic
    def post(self, request):
        vendor_id = request.data.get("vendor_id") or request.data.get("vendor")
        location_id = request.data.get("location_id") or request.data.get("location")
        po_id = request.data.get("po_id")
        lines = request.data.get("lines") or []
        if not vendor_id or not location_id or not po_id or not lines:
            return Response({"detail": "vendor_id, location_id, po_id and lines required"}, status=status.HTTP_400_BAD_REQUEST)

        # Build GRN DRAFT with lines; map to po_line by product
        from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
        grn = GoodsReceipt.objects.create(po_id=po_id, location_id=location_id, status=GoodsReceipt.Status.DRAFT)
        for ln in lines:
            product_id = ln.get("product_id")
            if not product_id:
                vend_code = ln.get("vendor_code") or ln.get("product_code") or ""
                prod = product_by_vendor_code(int(vendor_id), vend_code)
                if not prod:
                    return Response({"detail": f"Unable to resolve product for code '{vend_code}'"}, status=status.HTTP_400_BAD_REQUEST)
                product_id = prod.id
            pol = PurchaseOrderLine.objects.filter(po_id=po_id, product_id=product_id).first()
            if not pol:
                return Response({"detail": f"No PO line found for product {product_id}"}, status=status.HTTP_400_BAD_REQUEST)
            GoodsReceiptLine.objects.create(
                grn=grn,
                po_line=pol,
                product_id=product_id,
                batch_no=ln.get("batch_no", ""),
                mfg_date=ln.get("mfg_date"),
                expiry_date=ln.get("expiry_date"),
                qty_packs_received=int(ln.get("qty") or ln.get("qty_packs") or ln.get("qty_packs_received") or 0),
                qty_base_received=Decimal("0.000"),
                qty_base_damaged=Decimal("0.000"),
                unit_cost=Decimal(str(ln.get("unit_cost") or ln.get("price") or 0)),
                mrp=Decimal(str(ln.get("mrp") or 0)),
            )
        audit(request.user if request.user.is_authenticated else None, table="procurement_goodsreceipt", row_id=grn.id, action="IMPORT_COMMIT", before=None, after={"lines": len(lines)})
        return Response({"id": grn.id, "status": grn.status}, status=status.HTTP_201_CREATED)


class PurchasesMonthlyStatsView(APIView):
    @extend_schema(
        tags=["Procurement"],
        summary="Monthly purchases value series (from posted GRNs)",
        parameters=[OpenApiParameter("months", OpenApiTypes.INT, OpenApiParameter.QUERY), OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        months = int(request.query_params.get("months", 6))
        location_id = request.query_params.get("location_id")
        from .models import GoodsReceiptLine, GoodsReceipt
        qs = GoodsReceiptLine.objects.select_related("grn")
        if location_id:
            qs = qs.filter(grn__location_id=location_id)
        qs = qs.filter(grn__status=GoodsReceipt.Status.POSTED)
        data = (
            qs.annotate(month=TruncMonth("grn__received_at"))
            .values("month")
            .annotate(total=Sum(Sum("qty_packs_received") * 0 + Sum("unit_cost")))
        )
        # Simpler: compute value as sum(qty_packs_received * unit_cost)
        data = (
            qs.annotate(month=TruncMonth("grn__received_at"))
            .values("month")
            .annotate(value=Sum(Sum("qty_packs_received") * 0))
        )
        # We'll compute value in Python to avoid DB-specific operations
        from collections import defaultdict
        bucket = defaultdict(lambda: 0)
        for gl in qs.annotate(month=TruncMonth("grn__received_at")).values(
            "month", "qty_packs_received", "unit_cost"
        ):
            if gl["month"] is None:
                continue
            key = gl["month"].strftime("%Y-%m")
            bucket[key] += float(gl["qty_packs_received"] or 0) * float(gl["unit_cost"] or 0)
        # Keep only latest N months sorted
        series = [{"month": k, "total": round(v, 2)} for k, v in sorted(bucket.items())][-months:]
        return Response(series)

