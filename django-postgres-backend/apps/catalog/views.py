from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, permissions
from django.db import models
from drf_spectacular.utils import extend_schema, OpenApiTypes
from django.utils import timezone
from datetime import timedelta
from .models import ProductCategory, Product, BatchLot, MedicineForm, Uom, VendorProductCode
from .serializers import (
    ProductCategorySerializer, ProductSerializer, BatchLotSerializer,
    MedicineFormSerializer, UomSerializer, VendorProductCodeSerializer,
)
from apps.procurement.models import Vendor
from apps.procurement.serializers import VendorSerializer


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"ok": True})


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(models.Q(name__icontains=q) | models.Q(description__icontains=q))
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        ordering = self.request.query_params.get("ordering")
        if ordering in ("name", "-name", "created_at", "-created_at"):
            qs = qs.order_by(ordering)
        return qs


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ["category", "is_active"]
    search_fields = ["code", "name", "generic_name", "manufacturer"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                models.Q(code__icontains=q) | models.Q(name__icontains=q) | models.Q(generic_name__icontains=q) | models.Q(manufacturer__icontains=q)
            )
        low_stock = self.request.query_params.get("low_stock")
        if low_stock and low_stock.lower() == 'true':
            from apps.inventory.services import stock_summary
            from apps.settingsx.services import get_setting
            default_low = int(get_setting("ALERT_LOW_STOCK_DEFAULT", "50") or 50)
            low_ids = []
            # naive per-product aggregation
            rows = stock_summary()
            per_product = {}
            for r in rows:
                pid = r.get('product_id')
                per_product[pid] = per_product.get(pid, 0) + (r.get('stock_base') or 0)
            for pid, qty in per_product.items():
                p = Product.objects.filter(id=pid).first()
                thresh = p.reorder_level if p and p.reorder_level is not None else default_low
                if thresh is not None and qty < thresh:
                    low_ids.append(pid)
            qs = qs.filter(id__in=low_ids or [-1])
        return qs


class BatchLotViewSet(viewsets.ModelViewSet):
    queryset = BatchLot.objects.all()
    serializer_class = BatchLotSerializer
    filterset_fields = ["product", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        days = self.request.query_params.get("expiring_within_days")
        if days:
            try:
                d = int(days)
                cutoff = timezone.now().date() + timedelta(days=d)
                qs = qs.filter(expiry_date__isnull=False, expiry_date__lte=cutoff)
            except ValueError:
                pass
        return qs


class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer


class MedicineFormViewSet(viewsets.ModelViewSet):
    queryset = MedicineForm.objects.all()
    serializer_class = MedicineFormSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(models.Q(name__icontains=q) | models.Q(description__icontains=q))
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        ordering = self.request.query_params.get("ordering")
        if ordering in ("name", "-name", "created_at", "-created_at"):
            qs = qs.order_by(ordering)
        return qs


class UomViewSet(viewsets.ModelViewSet):
    queryset = Uom.objects.all()
    serializer_class = UomSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(models.Q(name__icontains=q) | models.Q(description__icontains=q))
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        ordering = self.request.query_params.get("ordering")
        if ordering in ("name", "-name", "created_at", "-created_at"):
            qs = qs.order_by(ordering)
        return qs


class VendorProductCodeViewSet(viewsets.ModelViewSet):
    queryset = VendorProductCode.objects.all()
    serializer_class = VendorProductCodeSerializer
    filterset_fields = ["vendor", "product"]
    search_fields = ["vendor_code", "vendor_name_alias"]


class CatalogStatsView(APIView):
    @extend_schema(tags=["Catalog"], summary="Catalog stats (active products & categories)", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        from .models import ProductCategory, Product
        return Response({
            "total_products": Product.objects.filter(is_active=True).count(),
            "total_categories": ProductCategory.objects.filter(is_active=True).count(),
        })

