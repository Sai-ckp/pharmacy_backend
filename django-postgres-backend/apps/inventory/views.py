from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, permissions, viewsets, serializers
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter, OpenApiExample
from django.db.models import Q, Sum, F
from datetime import date
from decimal import Decimal

from apps.catalog.models import BatchLot, ProductCategory, Product
from .services import (
    stock_on_hand,
    write_movement,
    low_stock,
    near_expiry,
    inventory_stats,
    stock_summary,
    stock_status_for_quantity,
    global_inventory_rows,
    convert_quantity_to_base,
)
from .models import RackLocation, InventoryMovement
from apps.locations.models import Location
from .serializers import (
    RackLocationSerializer,
    AddMedicineRequestSerializer,
    AddMedicineResponseSerializer,
    UpdateMedicineRequestSerializer,
)
from apps.settingsx.services import get_setting
from django.db import transaction
from django.db.models import ProtectedError
from apps.inventory.models import BatchStock
from apps.settingsx.utils import get_stock_thresholds
from apps.settingsx.models import SettingKV
from apps.sales.models import SalesLine
from apps.transfers.models import TransferLine
from apps.procurement.models import VendorReturn, PurchaseOrderLine, GoodsReceiptLine
from apps.compliance.models import H1RegisterEntry, NDPSDailyEntry, RecallEvent
from core.permissions import HasActiveSystemLicense


LICENSED_PERMISSIONS = [permissions.IsAuthenticated, HasActiveSystemLicense]
LICENSED_ADMIN_PERMISSIONS = [permissions.IsAdminUser, HasActiveSystemLicense]


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

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
    permission_classes = LICENSED_ADMIN_PERMISSIONS
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
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True)
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        data = self.low_stock(int(location_id))
        return Response(data)


    @staticmethod
    def low_stock(location_id):
        low_threshold, critical_threshold = get_stock_thresholds()

        # Sum stock for each product by combining all batches
        products = (
            BatchStock.objects.filter(location_id=location_id)
            .values("batch__product", "batch__product__name")
            .annotate(total_qty=Sum("quantity"))
        )

        result = []
        for p in products:
            qty = float(p["total_qty"] or 0)

            # Determine status
            if qty <= 0:
                status = "OUT_OF_STOCK"
            elif qty <= critical_threshold:
                status = "CRITICAL"
            elif qty <= low_threshold:
                status = "LOW"
            else:
                status = "IN_STOCK"

            result.append({
                "product_id": p["batch__product"],
                "name": p["batch__product__name"],
                "quantity": qty,
                "status": status,
            })

        return result




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


class ExpiryAlertsView(APIView):
    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Inventory"],
        summary="Expiry alerts with configurable thresholds",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("bucket", OpenApiTypes.STR, OpenApiParameter.QUERY, description="critical|warning|safe|all"),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        bucket = (request.query_params.get("bucket") or "all").lower()

        try:
            from apps.settingsx.models import AlertThresholds
            thr = AlertThresholds.objects.first()
            crit_days = thr.critical_expiry_days if thr else int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
            warn_days = thr.warning_expiry_days if thr else int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        except Exception:
            crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
            warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        rows = near_expiry(days=warn_days, location_id=location_id)
        today = date.today()

        summary = {"critical": 0, "warning": 0, "safe": 0}
        items = []

        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None
            status_txt = "safe"
            if days_left is None:
                status_txt = "safe"
            elif days_left <= crit_days:
                status_txt = "critical"
            elif days_left <= warn_days:
                status_txt = "warning"

            summary[status_txt] += 1
            if bucket != "all" and status_txt != bucket:
                continue
            items.append(
                {
                    "product_id": r.get("product_id"),
                    "batch_lot_id": r.get("batch_lot_id"),
                    "batch_no": r.get("batch_no"),
                    "expiry_date": exp,
                    "days_left": days_left,
                    "status": status_txt.upper(),
                    "quantity_base": float(r.get("stock_base") or 0),
                }
            )

        return Response({"summary": summary, "items": items})


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

class MedicineViewMixin:
    def _resolve_location_id(self, request, location):
        if location:
            try:
                return int(location)
            except (TypeError, ValueError):
                raise serializers.ValidationError({"location_id": "location_id must be an integer"})
        profile = getattr(request.user, "profile", None)
        if profile and getattr(profile, "location_id", None):
            return profile.location_id
        first = Location.objects.order_by("id").first()
        return first.id if first else None

    def _generate_code(self) -> str:
        last = Product.objects.order_by("-id").first()
        next_id = (last.id + 1) if last else 1
        return f"PRD-{next_id:05d}"

    def _purge_batch_dependencies(self, batch: BatchLot):
        SalesLine.objects.filter(batch_lot=batch).delete()
        VendorReturn.objects.filter(batch_lot=batch).delete()
        RecallEvent.objects.filter(batch_lot=batch).delete()
        H1RegisterEntry.objects.filter(batch_lot=batch).update(batch_lot=None)
        TransferLine.objects.filter(batch_lot=batch).delete()

    def _purge_product_dependencies(self, product: Product):
        NDPSDailyEntry.objects.filter(product=product).delete()
        H1RegisterEntry.objects.filter(product=product).update(product=None)
        PurchaseOrderLine.objects.filter(product=product).update(product=None)
        GoodsReceiptLine.objects.filter(product=product).update(product=None)

    def _upsert_product(self, payload: dict) -> Product:
        product_id = payload.get("id")
        product = None
        if product_id:
            product = Product.objects.select_for_update().filter(id=product_id).first()
            if not product:
                raise serializers.ValidationError({"id": "Medicine not found."})
        if not product:
            product = Product()
            product.code = payload.get("code") or self._generate_code()
        product.name = payload["name"]
        product.generic_name = payload.get("generic_name") or ""
        product.dosage_strength = payload.get("strength") or ""
        product.category = payload.get("category")
        product.medicine_form = payload.get("medicine_form")
        # UOMs are optional - will be inferred if not provided
        product.base_uom = payload.get("base_uom")
        product.selling_uom = payload.get("selling_uom")
        product.units_per_pack = payload.get("units_per_pack") or Decimal("1.000")
        product.base_unit_step = Decimal("1.000")
        product.mrp = payload.get("mrp")
        product.gst_percent = payload.get("gst_percent")
        product.description = payload.get("description") or ""
        # Set legacy char fields for backward compatibility
        if product.base_uom:
            product.base_unit = product.base_uom.name or "UNIT"
        else:
            product.base_unit = payload.get("base_unit") or "UNIT"
        if product.selling_uom:
            product.pack_unit = product.selling_uom.name or "PACK"
        else:
            product.pack_unit = payload.get("pack_unit") or "PACK"
        
        # Set default UOMs if not provided (for backward compatibility)
        # The Product model's save() method will handle setting base_unit and pack_unit from UOMs
        if not product.base_uom:
            try:
                from apps.catalog.models import Uom
                # Try common base UOMs
                for uom_name in ["TAB", "ML", "GM", "UNIT"]:
                    default_uom = Uom.objects.filter(name__iexact=uom_name).first()
                    if default_uom:
                        product.base_uom = default_uom
                        break
            except:
                pass
        
        if not product.selling_uom:
            try:
                from apps.catalog.models import Uom
                # Try common selling UOMs
                for uom_name in ["STRIP", "BOTTLE", "TUBE", "PACK"]:
                    default_uom = Uom.objects.filter(name__iexact=uom_name).first()
                    if default_uom:
                        product.selling_uom = default_uom
                        break
                # If still not set, use base_uom
                if not product.selling_uom and product.base_uom:
                    product.selling_uom = product.base_uom
            except:
                if product.base_uom:
                    product.selling_uom = product.base_uom
        # Tablet/Capsule packaging
        product.tablets_per_strip = payload.get("tablets_per_strip")
        product.capsules_per_strip = payload.get("capsules_per_strip")
        product.strips_per_box = payload.get("strips_per_box")
        # Liquid packaging
        product.ml_per_bottle = payload.get("ml_per_bottle")
        product.bottles_per_box = payload.get("bottles_per_box")
        # Injection/Vial packaging
        product.ml_per_vial = payload.get("ml_per_vial")
        product.vials_per_box = payload.get("vials_per_box")
        # Ointment/Cream/Gel packaging
        product.grams_per_tube = payload.get("grams_per_tube")
        product.tubes_per_box = payload.get("tubes_per_box")
        # Inhaler packaging
        product.doses_per_inhaler = payload.get("doses_per_inhaler")
        product.inhalers_per_box = payload.get("inhalers_per_box")
        # Powder/Sachet packaging
        product.grams_per_sachet = payload.get("grams_per_sachet")
        product.sachets_per_box = payload.get("sachets_per_box")
        # Soap/Bar packaging
        product.grams_per_bar = payload.get("grams_per_bar")
        product.bars_per_box = payload.get("bars_per_box")
        # Pack/Generic packaging
        product.pieces_per_pack = payload.get("pieces_per_pack")
        product.packs_per_box = payload.get("packs_per_box")
        # Gloves/Pairs packaging
        product.pairs_per_pack = payload.get("pairs_per_pack")
        # Cotton/Gauze packaging
        product.grams_per_pack = payload.get("grams_per_pack")
        # Units per pack (generic)
        product.units_per_pack = payload.get("units_per_pack")
        product.rack_location = payload.get("rack_location")
        product.is_active = True
        product.save()
        return product

    def _create_batch(self, product: Product, payload: dict) -> BatchLot:
        batch_no = payload["batch_number"]
        if BatchLot.objects.filter(product=product, batch_no=batch_no).exists():
            raise serializers.ValidationError({"batch_number": "Batch already exists for this medicine."})

        quantity = Decimal(str(payload["quantity"]))
        total_base_units = Decimal(payload["conversion_factor"])
        unit_factor = Decimal(payload.get("unit_factor") or total_base_units)
        purchase_price = Decimal(str(payload["purchase_price"]))
        price_per_base = Decimal("0.000000")
        if unit_factor <= 0 and total_base_units > 0 and quantity > 0:
            unit_factor = total_base_units / quantity
        if unit_factor > 0:
            price_per_base = purchase_price / unit_factor

        rack_code = product.rack_location.name if product.rack_location else ""
        batch = BatchLot.objects.create(
            product=product,
            batch_no=batch_no,
            mfg_date=payload.get("mfg_date"),
            expiry_date=payload.get("expiry_date"),
            status=BatchLot.Status.ACTIVE,
            rack_no=rack_code,
            quantity_uom=payload.get("quantity_uom"),
            initial_quantity=quantity,
            initial_quantity_base=total_base_units,
            purchase_price=purchase_price,
            purchase_price_per_base=price_per_base,
        )
        return batch

    def _update_batch(self, batch: BatchLot, payload: dict) -> BatchLot:
        quantity = Decimal(str(payload["quantity"]))
        total_base_units = Decimal(payload["conversion_factor"])
        unit_factor = Decimal(payload.get("unit_factor") or total_base_units)
        purchase_price = Decimal(str(payload["purchase_price"]))
        price_per_base = Decimal("0.000000")
        if unit_factor <= 0 and total_base_units > 0 and quantity > 0:
            unit_factor = total_base_units / quantity
        if unit_factor > 0:
            price_per_base = purchase_price / unit_factor

        batch.batch_no = payload["batch_number"]
        batch.mfg_date = payload.get("mfg_date")
        batch.expiry_date = payload.get("expiry_date")
        batch.quantity_uom = payload.get("quantity_uom")
        batch.initial_quantity = quantity
        batch.initial_quantity_base = total_base_units
        batch.purchase_price = purchase_price
        batch.purchase_price_per_base = price_per_base
        rack_code = batch.product.rack_location.name if batch.product.rack_location else ""
        batch.rack_no = rack_code
        batch.save()
        return batch

    @staticmethod
    def _ref(obj):
        if not obj:
            return None
        return {"id": obj.id, "name": getattr(obj, "name", "")}

    def _serialize_product(self, product: Product) -> dict:
        # Get category object - must return object with id and name for MasterRefSerializer
        # _ref returns None if object is None, but MasterRefSerializer needs an object
        category_obj = self._ref(product.category)
        if not category_obj:
            # Return a default object if category is None
            category_obj = {"id": 0, "name": ""}
        
        return {
            "id": product.id,
            "code": product.code,
            "name": product.name,
            "generic_name": product.generic_name,
            "strength": product.dosage_strength,
            "category": category_obj,  # Must be object with id and name for MasterRefSerializer
            "form": self._ref(product.medicine_form) or {"id": 0, "name": ""},
            "base_uom": self._ref(product.base_uom) or {"id": 0, "name": ""},
            "selling_uom": self._ref(product.selling_uom) or {"id": 0, "name": ""},
            "rack_location": self._ref(product.rack_location) or {"id": 0, "name": ""},
            "gst_percent": str(product.gst_percent or Decimal("0")),
            "description": product.description or "",
            "storage_instructions": product.storage_instructions or "",
            # Tablet/Capsule packaging
            "tablets_per_strip": product.tablets_per_strip,
            "capsules_per_strip": product.capsules_per_strip,
            "strips_per_box": product.strips_per_box,
            # Liquid packaging
            "ml_per_bottle": str(product.ml_per_bottle) if product.ml_per_bottle is not None else None,
            "bottles_per_box": product.bottles_per_box,
            # Injection/Vial packaging
            "ml_per_vial": str(product.ml_per_vial) if product.ml_per_vial is not None else None,
            "vials_per_box": product.vials_per_box,
            # Ointment/Cream/Gel packaging
            "grams_per_tube": str(product.grams_per_tube) if product.grams_per_tube is not None else None,
            "tubes_per_box": product.tubes_per_box,
            # Inhaler packaging
            "doses_per_inhaler": product.doses_per_inhaler,
            "inhalers_per_box": product.inhalers_per_box,
            # Powder/Sachet packaging
            "grams_per_sachet": str(product.grams_per_sachet) if product.grams_per_sachet is not None else None,
            "sachets_per_box": product.sachets_per_box,
            # Soap/Bar packaging
            "grams_per_bar": str(product.grams_per_bar) if product.grams_per_bar is not None else None,
            "bars_per_box": product.bars_per_box,
            # Pack/Generic packaging
            "pieces_per_pack": product.pieces_per_pack,
            "packs_per_box": product.packs_per_box,
            # Gloves/Pairs packaging
            "pairs_per_pack": product.pairs_per_pack,
            # Cotton/Gauze packaging
            "grams_per_pack": str(product.grams_per_pack) if product.grams_per_pack is not None else None,
            "units_per_pack": str(product.units_per_pack or Decimal("0")),
            "mrp": str(product.mrp or Decimal("0.00")),
            "status": "ACTIVE" if product.is_active else "INACTIVE",
        }

    def _serialize_batch(self, batch: BatchLot, stock_base: Decimal) -> dict:
        # Infer stock_unit from quantity_uom
        stock_unit = None
        if batch.quantity_uom:
            uom_name = (batch.quantity_uom.name or "").strip().upper()
            # Check if it's a box type UOM
            if uom_name in {"BOX", "BOXES", "CARTON", "CARTONS", "PACK", "PACKS"}:
                stock_unit = "box"
            else:
                stock_unit = "loose"
        
        return {
            "id": batch.id,
            "batch_number": batch.batch_no,
            "status": batch.status,
            "mfg_date": batch.mfg_date,
            "expiry_date": batch.expiry_date,
            "quantity": f"{batch.initial_quantity:.3f}",
            "quantity_uom": self._ref(batch.quantity_uom),
            "stock_unit": stock_unit,  # Add stock_unit to response
            "base_quantity": f"{batch.initial_quantity_base:.3f}",
            "purchase_price": f"{batch.purchase_price:.2f}",
            "purchase_price_per_base": f"{batch.purchase_price_per_base:.6f}",
            "current_stock_base": f"{stock_base:.3f}",
        }


class AddMedicineView(MedicineViewMixin, APIView):
    permission_classes = LICENSED_ADMIN_PERMISSIONS
    @extend_schema(
        tags=["Inventory"],
        summary="Add new medicine (master + first batch) in one call (Admin)",
        description="Creates/updates medicine master, opening batch, and inventory movement with base unit conversion.",
        request=AddMedicineRequestSerializer,
        responses={201: AddMedicineResponseSerializer, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Add Medicine",
                value={
                    "location_id": 1,
                    "medicine": {
                        "name": "Paracetamol 500mg",
                        "generic_name": "Acetaminophen",
                        "category": 2,
                        "form": 1,
                        "strength": "500 mg",
                        "base_uom": 5,
                        "selling_uom": 7,
                        "rack_location": 3,
                        "tablets_per_strip": 10,
                        "strips_per_box": 5,
                        "gst_percent": "5.00",
                        "mrp": "35.00",
                        "description": "Pain reliever"
                    },
                    "batch": {
                        "batch_number": "BTH-2024-078",
                        "mfg_date": "2024-06-01",
                        "expiry_date": "2026-05-31",
                        "quantity": 5,
                        "quantity_uom": 8,
                        "purchase_price": "350.00"
                    }
                },
            )
        ],
    )
    @transaction.atomic
    def post(self, request):
        serializer = AddMedicineRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        location_id = self._resolve_location_id(request, payload.get("location_id"))
        if not location_id:
            raise serializers.ValidationError({"location_id": "location_id is required"})

        medicine_payload = payload["medicine"]
        batch_payload = payload["batch"]

        product = self._upsert_product(medicine_payload)
        batch = self._create_batch(product, batch_payload)
        qty_base = Decimal(batch_payload["quantity_base"])

        movement_id = None
        # Allow both positive (add stock) and negative (reduce stock) quantities
        if qty_base != 0:
            reason = "ADJUSTMENT" if qty_base > 0 else "ADJUSTMENT"  # Use ADJUSTMENT for both
            movement_id = write_movement(
                location_id=int(location_id),
                batch_lot_id=batch.id,
                qty_change_base=qty_base,  # Can be negative to reduce stock
                reason=reason,
                ref_doc=("OPENING_STOCK", 0),
                actor=request.user if request.user.is_authenticated else None,
            )

        current_stock = stock_on_hand(int(location_id), batch.id)
        stock_state = stock_status_for_quantity(current_stock)

        response_payload = {
            "medicine": self._serialize_product(product),
            "batch": self._serialize_batch(batch, current_stock),
            "inventory": {
                "location_id": int(location_id),
                "movement_id": movement_id,
                "stock_status": stock_state,
                "stock_on_hand_base": f"{current_stock:.3f}",
            },
        }
        response_serializer = AddMedicineResponseSerializer(response_payload)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MedicineDetailView(MedicineViewMixin, APIView):
    permission_classes = LICENSED_PERMISSIONS

    def get_batch(self, batch_id: int) -> BatchLot:
        return BatchLot.objects.select_related(
            "product",
            "product__category",
            "product__medicine_form",
            "product__base_uom",
            "product__selling_uom",
            "product__rack_location",
            "quantity_uom",
        ).get(id=batch_id)

    def get(self, request, batch_id: int):
        location = request.query_params.get("location_id")
        location_id = self._resolve_location_id(request, location)
        try:
            batch = self.get_batch(batch_id)
        except BatchLot.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        stock_qty = stock_on_hand(location_id, batch.id) if location_id else Decimal("0")
        stock_state = stock_status_for_quantity(stock_qty)
        payload = {
            "medicine": self._serialize_product(batch.product),
            "batch": self._serialize_batch(batch, stock_qty),
            "inventory": {
                "location_id": location_id,
                "stock_status": stock_state,
                "stock_on_hand_base": f"{stock_qty:.3f}",
            },
        }
        return Response(payload)

    @transaction.atomic
    def put(self, request, batch_id: int):
        if not request.user.is_staff:
            raise permissions.PermissionDenied("Only administrators can update medicines.")
        serializer = UpdateMedicineRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        location_id = self._resolve_location_id(request, payload.get("location_id"))
        try:
            batch = self.get_batch(batch_id)
        except BatchLot.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        batch_payload = payload["batch"]
        if batch_payload.get("id") != batch_id:
            raise serializers.ValidationError({"batch": "Batch id mismatch."})
        medicine_payload = payload["medicine"]
        if not medicine_payload.get("id"):
            medicine_payload["id"] = batch.product_id
        product = self._upsert_product(medicine_payload)
        
        # Calculate stock difference: treat entered quantity as addition to CURRENT stock
        # Get current stock on hand in base units (actual stock after all movements)
        current_stock_base = stock_on_hand(location_id, batch.id) if location_id else Decimal("0")
        
        # Get the entered quantity from payload
        entered_qty_ui = Decimal(str(batch_payload.get("quantity", 0)))
        stock_unit_new = batch_payload.get("stock_unit") or "loose"
        
        # Infer old stock unit from batch's quantity_uom (batch doesn't have stock_unit field)
        stock_unit_old = "loose"
        if batch.quantity_uom:
            uom_name = (batch.quantity_uom.name or "").strip().upper()
            if uom_name in {"BOX", "BOXES", "CARTON", "CARTONS", "PACK", "PACKS"}:
                stock_unit_old = "box"
            else:
                stock_unit_old = "loose"
        
        # Handle None values for UOMs
        base_uom = product.base_uom if hasattr(product, 'base_uom') else None
        selling_uom = product.selling_uom if hasattr(product, 'selling_uom') else None
        
        # Calculate the quantity change based on whether stock units match
        if stock_unit_new == stock_unit_old:
            # Same stock unit: frontend sends total (current + change)
            # Calculate change: new_total_base - current_stock_base
            try:
                new_total_base, _ = convert_quantity_to_base(
                    quantity=entered_qty_ui,
                    base_uom=base_uom,
                    selling_uom=selling_uom,
                    quantity_uom=batch_payload.get("quantity_uom"),
                    units_per_pack=product.units_per_pack or Decimal("1"),
                    stock_unit=stock_unit_new,
                    tablets_per_strip=medicine_payload.get("tablets_per_strip"),
                    capsules_per_strip=medicine_payload.get("capsules_per_strip"),
                    strips_per_box=medicine_payload.get("strips_per_box"),
                    ml_per_bottle=medicine_payload.get("ml_per_bottle"),
                    bottles_per_box=medicine_payload.get("bottles_per_box"),
                    ml_per_vial=medicine_payload.get("ml_per_vial"),
                    grams_per_tube=medicine_payload.get("grams_per_tube"),
                    tubes_per_box=medicine_payload.get("tubes_per_box"),
                    vials_per_box=medicine_payload.get("vials_per_box"),
                    grams_per_sachet=medicine_payload.get("grams_per_sachet"),
                    sachets_per_box=medicine_payload.get("sachets_per_box"),
                    grams_per_bar=medicine_payload.get("grams_per_bar"),
                    bars_per_box=medicine_payload.get("bars_per_box"),
                    pieces_per_pack=medicine_payload.get("pieces_per_pack"),
                    packs_per_box=medicine_payload.get("packs_per_box"),
                    pairs_per_pack=medicine_payload.get("pairs_per_pack"),
                    grams_per_pack=medicine_payload.get("grams_per_pack"),
                    doses_per_inhaler=medicine_payload.get("doses_per_inhaler"),
                    inhalers_per_box=medicine_payload.get("inhalers_per_box"),
                )
                # Calculate difference: new total - current stock
                qty_diff = new_total_base - current_stock_base
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error converting quantity to base: {e}", exc_info=True)
                raise serializers.ValidationError({
                    "quantity": f"Error calculating stock: {str(e)}"
                })
        else:
            # Different stock unit: frontend sends just the change amount (not total)
            # Convert the entered quantity directly to base units and add to current stock
            try:
                qty_change_base, _ = convert_quantity_to_base(
                    quantity=entered_qty_ui,  # This is the change amount, not total
                    base_uom=base_uom,
                    selling_uom=selling_uom,
                    quantity_uom=batch_payload.get("quantity_uom"),
                    units_per_pack=product.units_per_pack or Decimal("1"),
                    stock_unit=stock_unit_new,  # Use new stock unit for conversion
                    tablets_per_strip=medicine_payload.get("tablets_per_strip"),
                    capsules_per_strip=medicine_payload.get("capsules_per_strip"),
                    strips_per_box=medicine_payload.get("strips_per_box"),
                    ml_per_bottle=medicine_payload.get("ml_per_bottle"),
                    bottles_per_box=medicine_payload.get("bottles_per_box"),
                    ml_per_vial=medicine_payload.get("ml_per_vial"),
                    grams_per_tube=medicine_payload.get("grams_per_tube"),
                    tubes_per_box=medicine_payload.get("tubes_per_box"),
                    vials_per_box=medicine_payload.get("vials_per_box"),
                    grams_per_sachet=medicine_payload.get("grams_per_sachet"),
                    sachets_per_box=medicine_payload.get("sachets_per_box"),
                    grams_per_bar=medicine_payload.get("grams_per_bar"),
                    bars_per_box=medicine_payload.get("bars_per_box"),
                    pieces_per_pack=medicine_payload.get("pieces_per_pack"),
                    packs_per_box=medicine_payload.get("packs_per_box"),
                    pairs_per_pack=medicine_payload.get("pairs_per_pack"),
                    grams_per_pack=medicine_payload.get("grams_per_pack"),
                    doses_per_inhaler=medicine_payload.get("doses_per_inhaler"),
                    inhalers_per_box=medicine_payload.get("inhalers_per_box"),
                )
                # When units differ, the entered quantity is the change amount
                # Add it directly to current stock
                qty_diff = qty_change_base
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error converting quantity to base: {e}", exc_info=True)
                raise serializers.ValidationError({
                    "quantity": f"Error calculating stock: {str(e)}"
                })
        
        # Update the batch with the new total quantity
        updated_batch = self._update_batch(batch, batch_payload)
        
        # Create movement if quantity changed (can be positive or negative)
        movement_id = None
        if qty_diff != 0 and location_id:
            movement_id = write_movement(
                location_id=int(location_id),
                batch_lot_id=updated_batch.id,
                qty_change_base=qty_diff,  # Can be negative to reduce stock
                reason="ADJUSTMENT",
                ref_doc=("STOCK_UPDATE", batch_id),
                actor=request.user if request.user.is_authenticated else None,
            )
        
        stock_qty = stock_on_hand(location_id, updated_batch.id) if location_id else Decimal("0")
        stock_state = stock_status_for_quantity(stock_qty)
        response_payload = {
            "medicine": self._serialize_product(product),
            "batch": self._serialize_batch(updated_batch, stock_qty),
            "inventory": {
                "location_id": location_id,
                "movement_id": movement_id,
                "stock_status": stock_state,
                "stock_on_hand_base": f"{stock_qty:.3f}",
            },
        }
        return Response(response_payload)

    @transaction.atomic
    def delete(self, request, batch_id: int):
        if not request.user.is_staff:
            raise permissions.PermissionDenied("Only administrators can delete medicines.")
        try:
            batch = self.get_batch(batch_id)
        except BatchLot.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        product = batch.product
        self._purge_batch_dependencies(batch)
        batch.delete()
        if not product.batches.exists():
            self._purge_product_dependencies(product)
            product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_204_NO_CONTENT)

class MedicinesListView(APIView):
    """
    Aggregate view used by the UI to show current medicines/stock per batch at a location.
    """

    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Inventory"],
        summary="List medicines (per batch) with current stock at a location",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Search by code/name"),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response(
                {"detail": "location_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            location_id = int(location_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "location_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        q = request.query_params.get("q") or ""
        category_id = request.query_params.get("category_id")
        status_filter = (request.query_params.get("status") or "").upper()

        base_qs = (
            InventoryMovement.objects.filter(location_id=location_id)
            .values(
                "batch_lot_id",
                "batch_lot__batch_no",
                "batch_lot__expiry_date",
                "batch_lot__product_id",
                "batch_lot__product__code",
                "batch_lot__product__name",
                "batch_lot__product__manufacturer",
                "batch_lot__product__category_id",
                "batch_lot__product__mrp",
            )
            .annotate(quantity=Sum("qty_change_base"))
        )

        if q:
            q_lower = q.lower()
            base_qs = [
                r
                for r in base_qs
                if q_lower in (r.get("batch_lot__product__name") or "").lower()
                or q_lower in (r.get("batch_lot__product__code") or "").lower()
                or q_lower in (r.get("batch_lot__batch_no") or "").lower()
            ]

        if category_id:
            try:
                cat_id_int = int(category_id)
                base_qs = [r for r in base_qs if r.get("batch_lot__product__category_id") == cat_id_int]
            except ValueError:
                return Response({"detail": "category_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        cat_ids = {r["batch_lot__product__category_id"] for r in base_qs if r.get("batch_lot__product__category_id")}
        cat_map = {
            c.id: c.name for c in ProductCategory.objects.filter(id__in=cat_ids)
        } if cat_ids else {}

        low_default, _ = get_stock_thresholds()
        default_threshold = Decimal(str(low_default)) if low_default else None

        out = []
        for r in base_qs:
            qty = r.get("quantity") or Decimal("0")
            # include zero and negative as Out of Stock rows so UI can still show them
            status_txt = "OUT_OF_STOCK"
            threshold = default_threshold
            if qty > 0:
                if threshold and qty <= threshold:
                    status_txt = "LOW_STOCK"
                else:
                    status_txt = "IN_STOCK"
            row = {
                "id": r["batch_lot_id"],
                "medicine_id": r.get("batch_lot__product__code") or "",
                "batch_number": r.get("batch_lot__batch_no") or "",
                "medicine_name": r.get("batch_lot__product__name") or "",
                "category": cat_map.get(r.get("batch_lot__product__category_id")) or "",
                "manufacturer": r.get("batch_lot__product__manufacturer") or "",
                "quantity": float(qty),
                "mrp": float(r.get("batch_lot__product__mrp") or 0),
                "expiry_date": r.get("batch_lot__expiry_date"),
                "status": status_txt,
            }
            if not status_filter or status_txt == status_filter:
                out.append(row)

        return Response(out)


class GlobalMedicinesView(APIView):
    permission_classes = LICENSED_PERMISSIONS

    @extend_schema(
        tags=["Inventory"],
        summary="List inventory batches across all locations",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Search by code/name/batch"),
            OpenApiParameter("category_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("rack_id", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Rack location id"),
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        def _int_or_none(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        data = global_inventory_rows(
            search=request.query_params.get("q"),
            category_id=_int_or_none(request.query_params.get("category_id")),
            rack_id=_int_or_none(request.query_params.get("rack_id")),
            status=(request.query_params.get("status") or "").upper() or None,
            location_id=_int_or_none(request.query_params.get("location_id")),
        )
        return Response(data)


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

