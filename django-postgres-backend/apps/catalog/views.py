from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from django.utils import timezone
from datetime import timedelta
from .models import ProductCategory, Product, BatchLot
from .serializers import ProductCategorySerializer, ProductSerializer, BatchLotSerializer


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ["category", "is_active"]
    search_fields = ["name", "generic_name", "manufacturer"]

    def get_queryset(self):
        qs = super().get_queryset()
        low_stock = self.request.query_params.get("low_stock")
        if low_stock and low_stock.lower() == 'true':
            from apps.inventory.services import stock_summary
            from apps.settingsx.models import Settings
            try:
                default_low = int(Settings.objects.get(key="low_stock_threshold_default").value)
            except Settings.DoesNotExist:
                default_low = None
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

