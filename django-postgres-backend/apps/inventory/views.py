from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status
from django.db.models import Sum, F

from .models import InventoryLedger
from .services import stock_summary, low_stock, near_expiry
from apps.settingsx.models import Settings
from datetime import date


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class StockView(APIView):
    def get(self, request):
        location_id = request.query_params.get("location_id")
        product_id = request.query_params.get("product_id")
        batch_lot_id = request.query_params.get("batch_lot_id")
        rows = stock_summary(location_id=location_id, product_id=product_id, batch_lot_id=batch_lot_id)
        # Enrich with low_stock_flag and expiring_in_days (best-effort)
        try:
            default_low = int(Settings.objects.get(key="low_stock_threshold_default").value)
        except Settings.DoesNotExist:
            default_low = None
        enriched = []
        for r in rows:
            pid = r.get('product_id')
            from apps.catalog.models import Product, BatchLot
            p = Product.objects.filter(id=pid).first()
            b = BatchLot.objects.filter(id=r.get('batch_lot_id')).first()
            low_threshold = p.reorder_level if p and p.reorder_level is not None else default_low
            low_flag = False
            if low_threshold is not None and r.get('stock_base') is not None:
                low_flag = r['stock_base'] < low_threshold
            days = None
            if b and b.expiry_date:
                days = (b.expiry_date - date.today()).days
            r2 = dict(r)
            r2['low_stock_flag'] = low_flag
            r2['expiring_in_days'] = days
            enriched.append(r2)
        return Response(enriched)


class LowStockView(APIView):
    def get(self, request):
        location_id = request.query_params.get("location_id")
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        data = low_stock(location_id=int(location_id))
        return Response(data)


class ExpirySoonView(APIView):
    def get(self, request):
        location_id = request.query_params.get("location_id")
        days = request.query_params.get("days")
        days = int(days) if days else None
        data = near_expiry(days=days, location_id=location_id)
        return Response(data)

