from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status, permissions
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiExample, OpenApiParameter
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, InvalidOperation



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
from django.shortcuts import get_object_or_404
import logging
from apps.locations.models import Location


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"ok": True})


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by("name")
    serializer_class = VendorSerializer

    # -----------------------------
    # Vendor Summary (totals)
    # -----------------------------
    @extend_schema(
        tags=["Procurement"],
        summary="Vendor summary: totals and counts",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        from django.db.models import Sum

        v = self.get_object()
        pos = PurchaseOrder.objects.filter(vendor_id=v.id)

        total_orders = pos.count()
        total_amount = pos.aggregate(s=Sum("net_total")).get("s") or 0

        # DISTINCT requested item names instead of product_id
        prod_count = (
            PurchaseOrderLine.objects
            .filter(po__vendor_id=v.id)
            .values("requested_name")
            .distinct()
            .count()
        )

        return Response({
            "vendor_id": v.id,
            "total_orders": total_orders,
            "total_amount": float(total_amount),
            "products": prod_count,
        })

    # -----------------------------
    # Vendor PO List
    # -----------------------------
    @extend_schema(
        tags=["Procurement"],
        summary="Vendor purchase orders list (compact)",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="purchase-orders")
    def vendor_pos(self, request, pk=None):
        v = self.get_object()
        items = []

        for po in (
            PurchaseOrder.objects
            .filter(vendor_id=v.id)
            .order_by("-order_date")[:100]
        ):
            item_cnt = sum((l.qty_packs_ordered or 0) for l in po.lines.all())

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

    # -----------------------------
    # Vendor Products (using requested_name since no product FK)
    # -----------------------------
    @extend_schema(
        tags=["Procurement"],
        summary="Vendor supplied item names with last price/date",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="products")
    def vendor_products(self, request, pk=None):
        v = self.get_object()
        from .models import GoodsReceiptLine, GoodsReceipt

        # GRN IDs (posted only)
        grn_ids = GoodsReceipt.objects.filter(
            po__vendor_id=v.id,
            status=GoodsReceipt.Status.POSTED
        ).values_list("id", flat=True)

        qs = GoodsReceiptLine.objects.filter(grn_id__in=list(grn_ids))

        last_map = {}

        # --- Use GRN lines first ---
        for gl in qs.order_by("-grn__received_at"):

            # FIX: determine the item name safely
            if gl.product:
                key = gl.product.name
            elif gl.po_line and gl.po_line.requested_name:
                key = gl.po_line.requested_name
            else:
                key = "(Unnamed Item)"

            if key not in last_map:
                last_map[key] = {
                    "item_name": key,
                    "last_price": float(gl.unit_cost or 0),
                    "last_order_date": gl.grn.received_at,
                }

        # --- Fallback to PO lines if no GRN exists ---
        if not last_map:
            for pl in (
                PurchaseOrderLine.objects
                .filter(po__vendor_id=v.id)
                .order_by("-po__order_date")
            ):
                key = pl.requested_name or "(Unnamed Item)"

                if key not in last_map:
                    last_map[key] = {
                        "item_name": key,
                        "last_price": float(pl.expected_unit_cost or 0),
                        "last_order_date": pl.po.order_date,
                    }

        # Convert datetime to string
        result = []
        for item in last_map.values():
            result.append({
                "item_name": item["item_name"],
                "last_price": item["last_price"],
                "last_order_date": (
                    item["last_order_date"].strftime("%d-%m-%Y")
                    if item["last_order_date"]
                    else None
                ),
            })

        return Response(result)




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
        # Global vendor and location
        global_vendor_id = request.data.get("vendor_id") or request.data.get("vendor")
        location_id = request.data.get("location_id") or request.data.get("location")
        lines = request.data.get("lines") or []

        if not location_id or not isinstance(lines, list) or not lines:
            return Response({"detail": "location_id and lines required"}, status=status.HTTP_400_BAD_REQUEST)

        from collections import defaultdict
        vendor_lines = defaultdict(list)

        # Group by vendor
        for ln in lines:
            ln_vendor_id = ln.get("vendor_id") or ln.get("vendor") or global_vendor_id
            if not ln_vendor_id:
                return Response(
                    {"detail": "vendor_id is required either globally or per line."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                ln_vendor_id = int(ln_vendor_id)
            except (TypeError, ValueError):
                return Response({"detail": f"Invalid vendor id: {ln_vendor_id!r}"}, status=status.HTTP_400_BAD_REQUEST)

            vendor_lines[ln_vendor_id].append(ln)

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

                # Product always optional for PO (NO creation)
                product_id = ln.get("product_id") or ln.get("product")

                # PO only stores names when no product found
                requested_name = (
                    ln.get("requested_name")
                    or ln.get("product_name")
                    or ln.get("name")
                    or ""
                ).strip()

                # If no product_id → must have a requested_name
                if not product_id and not requested_name:
                    return Response(
                        {"detail": "requested_name is required when product_id is missing."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # DO NOT USE vendor_code → because it may trigger product lookup
                # Removed: product_by_vendor_code()
                # Removed: medicine_form logic

                line_payload = {
                    "product": product_id,  # May be None (allowed)
                    "requested_name": requested_name,
                    "qty_packs_ordered": (
                        ln.get("qty")
                        or ln.get("qty_packs")
                        or ln.get("qty_packs_ordered")
                        or 0
                    ),
                    "expected_unit_cost": (
                        ln.get("unit_cost")
                        or ln.get("price")
                        or ln.get("expected_unit_cost")
                        or "0.00"
                    ),
                    "gst_percent_override": ln.get("gst_percent") or ln.get("gst_percent_override"),
                }

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

        # Same response format
        if len(po_results) == 1:
            return Response(po_results[0], status=status.HTTP_201_CREATED)

        primary = po_results[0]
        primary["extra_po_ids"] = [
            p.get("id") for p in po_results[1:] if isinstance(p, dict)
        ]
        primary["extra_pos_count"] = len(primary["extra_po_ids"])
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


    
logger = logging.getLogger(__name__)


class PurchasePDFImportView(APIView):

    def post(self, request):
        file = request.FILES.get("file")
        vendor_id = request.data.get("vendor_id")
        location_id = request.data.get("location_id")
        auto_receive = request.data.get("auto_receive") in ["1", "true", "True", True]
        po_number = next_doc_number("PO")

        if not file:
            return Response({"detail": "file is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not vendor_id or not location_id:
            return Response({"detail": "vendor_id and location_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        tmp_path = None
        try:
            vendor = get_object_or_404(Vendor, pk=vendor_id)
            location = get_object_or_404(Location, pk=location_id)

            # TEMP SAVE PDF
            tmp_path = default_storage.save(f"temp_pdfs/{file.name}", file)
            tmp_full_path = default_storage.path(tmp_path)

            # PDF PARSE
            items = extract_purchase_items_from_pdf(tmp_full_path)
            if not items:
                return Response({"detail": "no items extracted from PDF"}, status=status.HTTP_400_BAD_REQUEST)

            created_lines = 0
            total_amount = Decimal("0.00")

            with transaction.atomic():

                po = PurchaseOrder.objects.create(
                    vendor=vendor,
                    location=location,
                    po_number=po_number,
                    order_date=timezone.now().date(),
                    status="OPEN",
                    net_total=0,
                )

                for it in items:
                    code = (it.get("product_code") or "").strip()
                    name = (it.get("name") or "").strip()

                    # -----------------------------------------
                    # PRODUCT LOOKUP (allowed, but NOT creation)
                    # -----------------------------------------
                    product = None

                    if code:
                        product = Product.objects.filter(code__iexact=code).first()

                    if not product and name:
                        product = Product.objects.filter(name__iexact=name).first()

                    if not product and name:
                        product = Product.objects.filter(name__icontains=name).first()

                    if not product and name:
                        first_token = name.split()[0]
                        product = Product.objects.filter(name__icontains=first_token).first()

                    # -----------------------------------------
                    # PRODUCT CREATION REMOVED COMPLETELY
                    # product stays None
                    # -----------------------------------------

                    # -----------------------------------------
                    # PARSE NUMERIC FIELDS
                    # -----------------------------------------
                    qty_raw = it.get("qty") or 0
                    rate_raw = it.get("rate") or 0
                    net_value_raw = it.get("net_value") or 0

                    try:
                        qty_packs = int(float(qty_raw))
                    except:
                        qty_packs = 0

                    try:
                        expected_unit_cost = Decimal(str(rate_raw))
                    except:
                        expected_unit_cost = Decimal("0.00")

                    try:
                        net_value = Decimal(str(net_value_raw))
                    except:
                        net_value = expected_unit_cost * qty_packs

                    # -----------------------------------------
                    # CREATE PO LINE
                    # -----------------------------------------
                    PurchaseOrderLine.objects.create(
                        po=po,
                        requested_name=name or (product.name if product else ""),
                        qty_packs_ordered=qty_packs,
                        expected_unit_cost=expected_unit_cost,
                        gst_percent_override=None
                    )

                    total_amount += net_value
                    created_lines += 1

                # -----------------------------------------
                # UPDATE TOTALS
                # -----------------------------------------
                po.net_total = total_amount
                po.save()

                # auto-receive placeholder
                if auto_receive and created_lines:
                    logger.info("auto_receive requested but not implemented.")

            return Response({
                "message": "imported",
                "purchase_order_id": po.id,
                "po_number": po.po_number,
                "lines_created": created_lines,
                "net_total": str(po.net_total),
            }, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.exception("Error importing purchase PDF: %s", exc)
            return Response({
                "detail": "error importing PDF",
                "error": str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            if tmp_path and default_storage.exists(tmp_path):
                default_storage.delete(tmp_path)



def generate_product_code(name, units_per_pack):
    # NAME PART (first 4 letters uppercase)
    name_part = ''.join([c for c in name if c.isalpha()])[:4].upper()
    if not name_part:
        name_part = "PRD"

    # DIGITS FROM NAME
    digits = ''.join([c for c in name if c.isdigit()])

    # Fall back to no digits if name has none
    if not digits:
        digits = "0"

    # UNITS PER PACK
    up = str(units_per_pack)

    return f"{name_part}{digits}{up}"



    
