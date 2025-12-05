from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import models
from django.db.models import Sum
from django.db.models.functions import TruncMonth, Coalesce, Cast
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter

from apps.catalog.models import Product
from apps.inventory import services as inventory_services
from apps.locations.models import Location
from apps.procurement.models import Purchase
from apps.sales.models import SalesInvoice


class BaseDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_location_id(self, request) -> int | None:
        loc = request.query_params.get("location_id")
        if loc:
            try:
                return int(loc)
            except (TypeError, ValueError):
                raise ValueError("location_id must be an integer")
        profile = getattr(request.user, "profile", None)
        if profile and getattr(profile, "location_id", None):
            return profile.location_id
        first = Location.objects.order_by("id").first()
        return first.id if first else None


class DashboardSummaryView(BaseDashboardView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Dashboard summary metrics",
        parameters=[
            OpenApiParameter(
                "location_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Optional location context",
            )
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            location_id = self._resolve_location_id(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        location_name = None
        if location_id:
            location = Location.objects.filter(id=location_id).first()
            location_name = location.name if location else None

        total_medicines = Product.objects.filter(is_active=True).count()

        low_stock_rows = []
        inventory_status = {"in_stock": 0, "low_stock": 0, "out_of_stock": 0}
        if location_id:
            low_stock_rows = inventory_services.low_stock(location_id)
            inventory_status = inventory_services.inventory_stats(location_id)

        today = timezone.now().date()
        today_qs = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED, invoice_date__date=today
        )
        today_sales_amount = today_qs.aggregate(total=Sum("net_total")).get("total") or Decimal("0")
        today_sales_count = today_qs.count()

        pending_qs = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED, outstanding__gt=0
        )
        pending_bills = pending_qs.count()
        pending_amount = pending_qs.aggregate(total=Sum("outstanding")).get("total") or Decimal("0")

        recent_sales = self._recent_sales(limit=5, location_id=location_id)
        low_stock_list = self._serialize_low_stock(low_stock_rows[:5])

        data = {
            "totals": {
                "medicines": total_medicines,
                "low_stock": len(low_stock_rows),
            },
            "sales": {
                "today_amount": str(today_sales_amount),
                "today_bills": today_sales_count,
                "pending_bills": pending_bills,
                "pending_amount": str(pending_amount),
            },
            "inventory": {
                "status": inventory_status,
                "location_id": location_id,
                "location_name": location_name,
            },
            "recent_sales": recent_sales,
            "low_stock_items": low_stock_list,
        }
        return Response(data)

    def _recent_sales(self, limit: int, location_id: int | None):
        qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)
        if location_id:
            qs = qs.filter(location_id=location_id)
        qs = qs.select_related("customer").order_by("-invoice_date")[:limit]
        rows = []
        for inv in qs:
            rows.append(
                {
                    "invoice_no": inv.invoice_no or inv.id,
                    "customer_name": getattr(inv.customer, "name", "-"),
                    "amount": str(inv.net_total),
                    "status": inv.payment_status,
                    "invoice_date": inv.invoice_date,
                }
            )
        return rows

    def _serialize_low_stock(self, rows):
        out = []
        for row in rows:
            out.append(
                {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name") or "",
                    "stock_base": float(row.get("stock_base", 0)),
                    "threshold": float(row.get("threshold", 0)),
                    "location_id": row.get("location_id"),
                }
            )
        return out


class MonthlyChartView(BaseDashboardView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Monthly sales and purchase totals",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        months = self._month_sequence(6)
        start_date = months[0]
        sales_rows = (
            SalesInvoice.objects.filter(
                status=SalesInvoice.Status.POSTED, invoice_date__date__gte=start_date
            )
            .annotate(month=TruncMonth("invoice_date"))
            .values("month")
            .annotate(total=Sum("net_total"))
        )
        sales_map = {
            row["month"].strftime("%Y-%m"): row["total"]
            for row in sales_rows
            if row.get("month")
        }

        purchase_rows = (
            Purchase.objects.annotate(
                eff_date=Coalesce(
                    "invoice_date",
                    Cast("created_at", output_field=models.DateField()),
                )
            )
            .filter(eff_date__gte=start_date)
            .annotate(month=TruncMonth("eff_date"))
            .values("month")
            .annotate(total=Sum("net_total"))
        )
        purchase_map = {
            row["month"].strftime("%Y-%m"): row["total"]
            for row in purchase_rows
            if row.get("month")
        }

        payload = []
        for month_start in months:
            key = month_start.strftime("%Y-%m")
            payload.append(
                {
                    "month": key,
                    "sales_total": str(sales_map.get(key) or Decimal("0")),
                    "purchases_total": str(purchase_map.get(key) or Decimal("0")),
                }
            )
        return Response(payload)

    def _month_sequence(self, count: int):
        today = date.today().replace(day=1)
        months = []
        for i in range(count - 1, -1, -1):
            months.append(today - relativedelta(months=i))
        return months


class InventoryStatusView(BaseDashboardView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Inventory status distribution",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            location_id = self._resolve_location_id(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not location_id:
            return Response({"detail": "No locations configured"}, status=status.HTTP_400_BAD_REQUEST)
        stats = inventory_services.inventory_stats(location_id)
        return Response({"location_id": location_id, "status": stats})


class RecentSalesView(BaseDashboardView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Recent sales",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            location_id = self._resolve_location_id(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        rows = DashboardSummaryView()._recent_sales(limit=10, location_id=location_id)
        return Response(rows)


class LowStockListView(BaseDashboardView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Low stock list",
        parameters=[
            OpenApiParameter(
                "location_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                required=True,
            )
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            location_id = self._resolve_location_id(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not location_id:
            return Response({"detail": "location_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        rows = inventory_services.low_stock(location_id)
        data = DashboardSummaryView()._serialize_low_stock(rows)
        return Response(data)
