from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets, status
from django.db.models import Sum, F

from .models import InventoryLedger
from .services import stock_summary, low_stock, near_expiry


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class StockView(APIView):
    def get(self, request):
        location_id = request.query_params.get("location_id")
        product_id = request.query_params.get("product_id")
        batch_lot_id = request.query_params.get("batch_lot_id")
        data = stock_summary(location_id=location_id, product_id=product_id, batch_lot_id=batch_lot_id)
        return Response(data)


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

