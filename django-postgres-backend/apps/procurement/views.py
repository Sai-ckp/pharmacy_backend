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
from apps.accounts.models import User as AccountsUser
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
import os
from django.core.files.storage import default_storage
from .models import Purchase, PurchaseLine
from apps.catalog.models import Product, BatchLot
from apps.procurement.utils_pdf import extract_purchase_items_from_pdf
from django.conf import settings


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    queryset = Vendor.objects.all().order_by("name")
    serializer_class = VendorSerializer

    @extend_schema(
        tags=["Procurement"],
        summary="Vendor summary: totals and counts",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        from django.db.models import Sum, Count
        v = self.get_object()
        pos = PurchaseOrder.objects.filter(vendor_id=v.id)
        total_orders = pos.count()
        total_amount = pos.aggregate(s=Sum("net_total")).get("s") or 0
        # products supplied = distinct products in PO lines
        prod_count = (
            v
            and PurchaseOrderLine.objects.filter(po__vendor_id=v.id)
            .values("product_id")
            .distinct()
            .count()
        )
        return Response({
            "vendor_id": v.id,
            "total_orders": total_orders,
            "total_amount": float(total_amount),
            "products": prod_count,
        })

    @extend_schema(
        tags=["Procurement"],
        summary="Vendor purchase orders list (compact)",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="purchase-orders")
    def vendor_pos(self, request, pk=None):
        v = self.get_object()
        items = []
        for po in PurchaseOrder.objects.filter(vendor_id=v.id).order_by("-order_date")[:100]:
            item_cnt = sum(l.qty_packs_ordered or 0 for l in po.lines.all())
            items.append({
                "po_id": po.id,
                "po_number": po.po_number,
                "order_date": po.order_date.strftime("%d-%m-%Y") if po.order_date else None,
                "expected_date": po.expected_date.strftime("%d-%m-%Y") if po.expected_date else None,
                "items": item_cnt,
                "amount": float(po.net_total or 0),
                "status": po.status,
            })
        return Response(items)

    @extend_schema(
        tags=["Procurement"],
        summary="Vendor supplied products with last price and last order date",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="products")
    def vendor_products(self, request, pk=None):
        v = self.get_object()
        from .models import GoodsReceiptLine, GoodsReceipt
        from django.db.models import Max
        # Use GRN lines for accurate last price/date
        grn_ids = GoodsReceipt.objects.filter(po__vendor_id=v.id, status=GoodsReceipt.Status.POSTED).values_list("id", flat=True)
        qs = GoodsReceiptLine.objects.filter(grn_id__in=list(grn_ids)).select_related("product")
        # Build last price and date per product
        last_map = {}
        for gl in qs.order_by("-grn__received_at"):
            pid = gl.product_id
            if pid not in last_map:
                last_map[pid] = {
                    "product_id": pid,
                    "product_name": gl.product.name,
                    "category": getattr(gl.product.category, "name", None),
                    "last_price": float(gl.unit_cost or 0),
                    "last_order_date": gl.grn.received_at,
                }
        # Fallback to PO lines if no GRN yet
        if not last_map:
            for pl in PurchaseOrderLine.objects.filter(po__vendor_id=v.id).select_related("product").order_by("-po__order_date"):
                pid = pl.product_id
                if pid not in last_map:
                    last_map[pid] = {
                        "product_id": pid,
                        "product_name": pl.product.name,
                        "category": getattr(pl.product.category, "name", None),
                        "last_price": float(pl.expected_unit_cost or 0),
                        "last_order_date": pl.po.order_date,
                    }
        return Response(list(last_map.values()))


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

    @extend_schema(
        tags=["Procurement"],
        summary="Create vendor return by batch (helper)",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="create-by-batch")
    @transaction.atomic
    def create_by_batch(self, request):
        from .models import PurchaseOrderLine, PurchaseOrder
        from apps.catalog.models import BatchLot
        batch_lot_id = request.data.get("batch_lot_id")
        qty_base = request.data.get("qty_base")
        reason = request.data.get("reason", "EXPIRY_RETURN")
        if not batch_lot_id or qty_base is None:
            return Response({"detail": "batch_lot_id and qty_base are required"}, status=status.HTTP_400_BAD_REQUEST)
        lot = get_object_or_404(BatchLot, pk=batch_lot_id)
        # Find latest PO line for this product and vendor via PO with same vendor as last GRN if possible
        pol = (
            PurchaseOrderLine.objects.filter(product_id=lot.product_id)
            .select_related("po")
            .order_by("-po__order_date")
            .first()
        )
        if not pol:
            return Response({"detail": "No purchase order line found for this product."}, status=status.HTTP_400_BAD_REQUEST)
        vr = VendorReturn.objects.create(
            vendor=pol.po.vendor,
            purchase_line=pol,
            batch_lot=lot,
            qty_base=qty_base,
            reason=reason,
        )
        return Response(VendorReturnSerializer(vr).data, status=status.HTTP_201_CREATED)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all().prefetch_related("lines")
    serializer_class = PurchaseOrderSerializer

    def perform_create(self, serializer):
        po_number = next_doc_number('PO')
        actor = None
        if self.request.user and self.request.user.is_authenticated:
            email = getattr(self.request.user, "email", None)
            if email:
                actor = AccountsUser.objects.filter(email=email).first()
        serializer.save(po_number=po_number, created_by=actor)

    @extend_schema(
        tags=["Procurement"],
        summary="Get full purchase order details including product info",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="detail")
    def detail(self, request, pk=None):
        po = self.get_object()
        lines_payload = []
        for ln in po.lines.select_related("product").all():
            prod = ln.product
            lines_payload.append(
                {
                    "id": ln.id,
                    "product_id": prod.id if prod else None,
                    "product_code": getattr(prod, "code", None),
                    "product_name": getattr(prod, "name", None) or ln.requested_name,
                    "requested_name": ln.requested_name,
                    "medicine_form": {
                        "id": ln.medicine_form_id,
                        "name": ln.medicine_form.name if ln.medicine_form_id else None,
                    },
                    "manufacturer": getattr(prod, "manufacturer", None),
                    "pack_size": getattr(prod, "pack_size", None),
                    "qty_packs_ordered": ln.qty_packs_ordered,
                    "expected_unit_cost": str(ln.expected_unit_cost),
                    "gst_percent_override": (
                        str(ln.gst_percent_override)
                        if ln.gst_percent_override is not None
                        else None
                    ),
                }
            )
        payload = {
            "id": po.id,
            "po_number": po.po_number,
            "status": po.status,
            "vendor": {
                "id": po.vendor_id,
                "name": po.vendor.name if po.vendor_id else None,
            },
            "location_id": po.location_id,
            "order_date": po.order_date.strftime("%d-%m-%Y") if po.order_date else None,
            "expected_date": po.expected_date.strftime("%d-%m-%Y") if po.expected_date else None,
            "note": po.note,
            "gross_total": str(po.gross_total),
            "tax_total": str(po.tax_total),
            "net_total": str(po.net_total),
            "lines": lines_payload,
        }
        return Response(payload)

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
        # Global vendor and location from payload
        global_vendor_id = request.data.get("vendor_id") or request.data.get("vendor")
        location_id = request.data.get("location_id") or request.data.get("location")
        lines = request.data.get("lines") or []
        if not location_id or not isinstance(lines, list) or not lines:
            return Response({"detail": "location_id and lines required"}, status=status.HTTP_400_BAD_REQUEST)

        # Allow either a single global vendor_id, or vendor per line.
        # Group lines by their effective vendor so that separate vendors
        # always receive separate POs instead of overriding each other.
        from collections import defaultdict

        vendor_lines = defaultdict(list)
        for ln in lines:
            ln_vendor_id = ln.get("vendor_id") or ln.get("vendor") or global_vendor_id
            if not ln_vendor_id:
                return Response(
                    {"detail": "vendor_id is required either globally or per line."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                vid_int = int(ln_vendor_id)
            except (TypeError, ValueError):
                return Response({"detail": f"Invalid vendor id: {ln_vendor_id!r}"}, status=status.HTTP_400_BAD_REQUEST)
            vendor_lines[vid_int].append(ln)

        po_results = []
        actor = request.user if request.user.is_authenticated else None

        for vendor_id, v_lines in vendor_lines.items():
            po_payload = {
                "vendor": vendor_id,
                "location": location_id,
                "order_date": request.data.get("order_date"),
                "expected_date": request.data.get("expected_date"),
                "note": request.data.get("note", ""),
                "lines": [],
            }
            for ln in v_lines:
                product_id = ln.get("product_id")
                requested_name = (ln.get("requested_name") or ln.get("product_name") or ln.get("name") or "").strip()
                medicine_form_id = ln.get("medicine_form_id") or ln.get("medicine_form")
                if not product_id:
                    vend_code = ln.get("vendor_code") or ln.get("product_code") or ""
                    if vend_code:
                        prod = product_by_vendor_code(int(vendor_id), vend_code)
                        if prod:
                            product_id = prod.id
                    if not product_id and not requested_name:
                        return Response(
                            {"detail": "Each line must include product_id or product_name."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                if not product_id and not medicine_form_id:
                    return Response(
                        {"detail": "medicine_form is required when adding a new product."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                line_payload = {
                    "product": product_id,
                    "medicine_form": medicine_form_id,
                    "qty_packs_ordered": ln.get("qty") or ln.get("qty_packs") or ln.get("qty_packs_ordered") or 0,
                    "expected_unit_cost": ln.get("unit_cost") or ln.get("price") or ln.get("expected_unit_cost") or "0.00",
                    "gst_percent_override": ln.get("gst_percent") or ln.get("gst_percent_override"),
                }
                if requested_name:
                    line_payload["requested_name"] = requested_name
                po_payload["lines"].append(line_payload)

            ser = PurchaseOrderSerializer(data=po_payload)
            ser.is_valid(raise_exception=True)
            po = ser.save()
            audit(
                actor,
                table="procurement_purchaseorder",
                row_id=po.id,
                action="IMPORT_COMMIT",
                before=None,
                after={"lines": len(po_payload["lines"])},
            )
            po_results.append(ser.data)

        # Backwards compatible response shape: if only one vendor,
        # return that PO as before; if multiple vendors, still return
        # the first PO but include IDs of additional POs for reference.
        if len(po_results) == 1:
            return Response(po_results[0], status=status.HTTP_201_CREATED)

        primary = po_results[0] if isinstance(po_results[0], dict) else {"primary": po_results[0]}
        extra_ids = [po_data.get("id") for po_data in po_results[1:] if isinstance(po_data, dict)]
        primary["extra_po_ids"] = extra_ids
        primary["extra_pos_count"] = len(extra_ids)
        return Response(primary, status=status.HTTP_201_CREATED)


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


    
class PurchasePDFImportView(APIView):
    """
    POST multipart/form-data:
      - file: pdf file
      - vendor_id: id
      - location_id: id
      - auto_receive: optional boolean (if present and true, create GRN + InventoryMovement)
    """

    def post(self, request):
        file = request.FILES.get("file")
        vendor_id = request.data.get("vendor_id")
        location_id = request.data.get("location_id")
        auto_receive = request.data.get("auto_receive") in ["1", "true", "True", True]

        if not file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not vendor_id or not location_id:
            return Response({"detail": "vendor_id and location_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Save temp file
        tmp_path = default_storage.save("temp_pdfs/" + file.name, file)
        tmp_full = default_storage.path(tmp_path) if hasattr(default_storage, 'path') else os.path.join(settings.MEDIA_ROOT, tmp_path)

        # Extract items
        items = extract_purchase_items_from_pdf(tmp_full)
        if not items:
            # cleanup
            try:
                default_storage.delete(tmp_path)
            except Exception:
                pass
            return Response({"detail": "no items extracted from PDF"}, status=status.HTTP_400_BAD_REQUEST)

        created_purchase = None
        created_lines = 0
        with transaction.atomic():
            purchase = Purchase.objects.create(
                vendor_id=vendor_id,
                location_id=location_id,
                vendor_invoice_no="",
                invoice_date=None,
                gross_total=0,
                tax_total=0,
                net_total=0,
            )

            total_net = 0
            for it in items:
                # find or create product
                product = None
                code = (it.get("product_code") or "").strip()
                name = (it.get("name") or "").strip()

                if code:
                    product = Product.objects.filter(code__iexact=code).first()
                if product is None and name:
                    product = Product.objects.filter(name__iexact=name).first()
                if product is None and name:
                    # fallback: try name contains
                    product = Product.objects.filter(name__icontains=name.split()[0]).first()

                if product is None:
                    # create product with minimal required fields
                    product = Product.objects.create(
                        code=code or None,
                        name=name or "UNKNOWN",
                        mrp=it.get("mrp") or 0,
                        base_unit="UNIT",
                        pack_unit=it.get("pack") or "PACK",
                        units_per_pack=1,
                    )

                # create PurchaseLine
                pl = PurchaseLine.objects.create(
                    purchase=purchase,
                    product=product,
                    batch_no=it.get("batch_no") or "",
                    expiry_date=it.get("expiry_date"),
                    qty_packs=int(it.get("qty") or 0),
                    unit_cost=it.get("rate") or 0,
                    mrp=it.get("mrp") or 0,
                )

                # if you added new fields to PurchaseLine (discount, cgst, etc.) set them here if present
                # example:
                # pl.discount_percent = it.get("discount_percent"); pl.save()

                total_net += float(it.get("net_value") or 0)
                created_lines += 1

            # update purchase totals
            purchase.net_total = total_net
            purchase.gross_total = total_net
            purchase.save()
            created_purchase = purchase

        # cleanup temp file
        try:
            default_storage.delete(tmp_path)
        except Exception:
            pass

        return Response({
            "message": "imported",
            "purchase_id": created_purchase.id,
            "lines_created": created_lines
        }, status=status.HTTP_201_CREATED)    
