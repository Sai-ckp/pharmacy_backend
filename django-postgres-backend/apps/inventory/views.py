from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, permissions, viewsets
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter, OpenApiExample
from django.db.models import Q
from datetime import date
from decimal import Decimal

from apps.catalog.models import BatchLot
from .services import stock_on_hand, write_movement, low_stock, near_expiry, inventory_stats, stock_summary
from .models import RackLocation
from .serializers import RackLocationSerializer
from apps.settingsx.services import get_setting
from django.db import transaction


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class BatchesListView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="List batch lots with optional filters",
        parameters=[
            OpenApiParameter("product_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("exp_range", OpenApiTypes.STR, OpenApiParameter.QUERY, description="YYYY-MM-DD:YYYY-MM-DD"),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        status_f = request.query_params.get("status")
        product_id = request.query_params.get("product_id")
        exp_range = request.query_params.get("exp_range")  # not fully implemented
        qs = BatchLot.objects.all()
        if status_f:
            qs = qs.filter(status=status_f)
        if product_id:
            qs = qs.filter(product_id=product_id)
        # exp_range can be like YYYY-MM-DD:YYYY-MM-DD; ignore for now if malformed
        if exp_range and ":" in exp_range:
            start, end = exp_range.split(":", 1)
            if start:
                qs = qs.filter(expiry_date__gte=start)
            if end:
                qs = qs.filter(expiry_date__lte=end)
        data = list(qs.values("id", "product_id", "batch_no", "mfg_date", "expiry_date", "status", "rack_no"))
        return Response(data)


class StockOnHandView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="Stock on hand for a batch at a location",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("batch_lot_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        batch_lot_id = request.query_params.get("batch_lot_id")
        if not location_id or not batch_lot_id:
            return Response({"detail": "location_id and batch_lot_id required"}, status=status.HTTP_400_BAD_REQUEST)
        qty = stock_on_hand(int(location_id), int(batch_lot_id))
        return Response({"qty_base": f"{qty:.3f}"})


class MovementsCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]
    @extend_schema(
        tags=["Inventory"],
        summary="Create an inventory movement (Admin)",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("Adjust IN", value={"location_id":1, "batch_lot_id":10, "qty_change_base":"100.000", "reason":"ADJUSTMENT"})]
    )
    def post(self, request):
        location_id = int(request.data.get("location_id"))
        batch_lot_id = int(request.data.get("batch_lot_id"))
        qty = request.data.get("qty_change_base")
        reason = request.data.get("reason", "ADJUSTMENT")
        try:
            qty_d = float(qty)
        except Exception:
            return Response({"detail": "qty_change_base must be decimal"}, status=status.HTTP_400_BAD_REQUEST)
        mov_id = write_movement(
            location_id=location_id,
            batch_lot_id=batch_lot_id,
            qty_change_base=Decimal(str(qty_d)),
            reason=reason,
            ref_doc=("ADJUSTMENT", 0),
            actor=request.user if request.user.is_authenticated else None,
        )
        return Response({"id": mov_id}, status=status.HTTP_201_CREATED)


class MovementsListView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="List inventory movements",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("batch_lot_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("reason", OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from .models import InventoryMovement
        qs = InventoryMovement.objects.all().order_by('-created_at')
        location_id = request.query_params.get("location_id")
        batch_lot_id = request.query_params.get("batch_lot_id")
        reason = request.query_params.get("reason")
        if location_id:
            qs = qs.filter(location_id=location_id)
        if batch_lot_id:
            qs = qs.filter(batch_lot_id=batch_lot_id)
        if reason:
            qs = qs.filter(reason=reason)
        data = list(qs.values('id','location_id','batch_lot_id','qty_change_base','reason','ref_doc_type','ref_doc_id','created_at'))
        return Response(data)


class LowStockView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="List low stock products at a location",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        data = low_stock(location_id=int(location_id))
        return Response(data)


class ExpiringView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="List expiring batches",
        parameters=[
            OpenApiParameter("window", OpenApiTypes.STR, OpenApiParameter.QUERY, description="warning|critical"),
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        window = request.query_params.get("window")
        days = None
        if window == "critical":
            days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
        elif window == "warning":
            days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        data = near_expiry(days=days, location_id=request.query_params.get("location_id"))
        return Response(data)


class InventoryStatsView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="Inventory status counts for a location",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        data = inventory_stats(int(location_id))
        return Response(data)


class StockSummaryView(APIView):
    @extend_schema(
        tags=["Inventory"],
        summary="Stock summary for product at a location",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("product_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        product_id = request.query_params.get("product_id")
        if not location_id or not product_id:
            return Response({"detail": "location_id and product_id required"}, status=status.HTTP_400_BAD_REQUEST)
        rows = stock_summary(location_id=location_id, product_id=product_id)
        return Response(rows)


class AddMedicineView(APIView):
    permission_classes = [permissions.IsAdminUser]
    @extend_schema(
        tags=["Inventory"],
        summary="Add new medicine (product + batch + opening stock) in one call (Admin)",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Add Medicine",
                value={
                    "location_id": 1,
                    "product": {
                        "code": "PARA500", "name": "Paracetamol 500mg", "mrp": "5.00",
                        "base_unit": "TAB", "pack_unit": "STRIP", "units_per_pack": "10.000"
                    },
                    "batch": {"batch_no": "BTH-2024-078", "expiry_date": "2025-12-20"},
                    "opening_qty_packs": "200"
                },
            )
        ],
    )
    @transaction.atomic
    def post(self, request):
        from apps.catalog.models import Product, BatchLot
        from apps.catalog.services import packs_to_base
        from decimal import Decimal

        product_data = request.data.get("product") or {}
        batch_data = request.data.get("batch") or {}
        location_id = request.data.get("location_id")
        opening_qty_base = request.data.get("opening_qty_base")
        opening_qty_packs = request.data.get("opening_qty_packs") or request.data.get("quantity")

        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve or create product
        product_id = product_data.get("id")
        product: Product | None = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()
        elif product_data.get("code"):
            product = Product.objects.filter(code=product_data.get("code")).first()
        if not product:
            required = ["name", "base_unit", "pack_unit", "units_per_pack", "mrp"]
            missing = [f for f in required if not product_data.get(f)]
            if missing:
                return Response({"detail": f"Missing product fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)
            product = Product.objects.create(
                code=product_data.get("code"),
                name=product_data.get("name"),
                generic_name=product_data.get("generic_name", ""),
                dosage_strength=product_data.get("dosage_strength", ""),
                hsn=product_data.get("hsn", ""),
                schedule=product_data.get("schedule", Product.Schedule.OTC),
                category_id=product_data.get("category") or product_data.get("category_id"),
                pack_size=product_data.get("pack_size", ""),
                manufacturer=product_data.get("manufacturer", ""),
                mrp=Decimal(str(product_data.get("mrp"))),
                base_unit=product_data.get("base_unit"),
                pack_unit=product_data.get("pack_unit"),
                units_per_pack=Decimal(str(product_data.get("units_per_pack"))),
                base_unit_step=Decimal(str(product_data.get("base_unit_step") or "1.000")),
                gst_percent=Decimal(str(product_data.get("gst_percent") or "0")),
                reorder_level=Decimal(str(product_data.get("reorder_level") or "0")),
                description=product_data.get("description", ""),
                storage_instructions=product_data.get("storage_instructions", ""),
                preferred_vendor_id=product_data.get("preferred_vendor") or product_data.get("preferred_vendor_id"),
                is_sensitive=bool(product_data.get("is_sensitive", False)),
                is_active=True,
            )

        # Create or upsert batch
        if not batch_data.get("batch_no"):
            return Response({"detail": "batch.batch_no is required"}, status=status.HTTP_400_BAD_REQUEST)
        batch, _ = BatchLot.objects.get_or_create(
            product=product,
            batch_no=batch_data.get("batch_no"),
            defaults={
                "mfg_date": batch_data.get("mfg_date"),
                "expiry_date": batch_data.get("expiry_date"),
                "status": BatchLot.Status.ACTIVE,
            },
        )
        # Fill missing attributes if provided
        changed = False
        if batch_data.get("mfg_date") and not batch.mfg_date:
            batch.mfg_date = batch_data.get("mfg_date"); changed = True
        if batch_data.get("expiry_date") and not batch.expiry_date:
            batch.expiry_date = batch_data.get("expiry_date"); changed = True
        if batch_data.get("rack_no") and not batch.rack_no:
            batch.rack_no = batch_data.get("rack_no"); changed = True
        if changed:
            batch.save()

        # Determine opening qty in base units
        qty_base = Decimal("0.000")
        if opening_qty_base is not None and str(opening_qty_base) != "":
            qty_base = Decimal(str(opening_qty_base))
        elif opening_qty_packs is not None and str(opening_qty_packs) != "":
            qty_base = packs_to_base(product.id, Decimal(str(opening_qty_packs)))

        movement_id = None
        if qty_base and qty_base > 0:
            movement_id = write_movement(
                location_id=int(location_id),
                batch_lot_id=batch.id,
                qty_change_base=qty_base,
                reason="ADJUSTMENT",
                ref_doc=("OPENING_STOCK", 0),
                actor=request.user if request.user.is_authenticated else None,
            )

        return Response(
            {
                "product_id": product.id,
                "batch_lot_id": batch.id,
                "movement_id": movement_id,
                "qty_base_written": f"{qty_base:.3f}",
            },
            status=status.HTTP_201_CREATED,
        )


class RackLocationViewSet(viewsets.ModelViewSet):
    queryset = RackLocation.objects.all()
    serializer_class = RackLocationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        ordering = self.request.query_params.get("ordering")
        if ordering in ("name", "-name", "created_at", "-created_at"):
            qs = qs.order_by(ordering)
        return qs

