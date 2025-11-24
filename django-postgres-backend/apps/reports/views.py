from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.db.models import Sum, Count
from datetime import date
from .models import ReportExport
from .serializers import ReportExportSerializer
from . import services
import os
from django.conf import settings
from django.http import FileResponse, Http404


class ReportExportViewSet(viewsets.ModelViewSet):
    queryset = ReportExport.objects.all().order_by("-created_at")
    serializer_class = ReportExportSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Create export record + return XLSX immediately without saving to disk.
        """

        # Validate & create record
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        export = serializer.save(
            status=ReportExport.Status.QUEUED,
            started_at=timezone.now(),
        )

        # Mark as running
        export.status = ReportExport.Status.RUNNING
        export.save(update_fields=["status", "started_at"])

        try:
            # 🔥 Generate XLSX in-memory (no filesystem)
            filename, buffer = services.generate_report_file(export)

            export.status = ReportExport.Status.DONE
            export.finished_at = timezone.now()
            export.file_path = filename     # store only filename (optional)
            export.save(update_fields=["status", "finished_at", "file_path"])

            # 🔥 Return Excel file directly
            response = FileResponse(
                buffer,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            export.status = ReportExport.Status.FAILED
            export.file_path = str(e)
            export.save(update_fields=["status", "file_path"])
            return Response({"error": str(e)}, status=500)

    @action(detail=False, methods=["get"], url_path="recent")
    def recent_exports(self, request):
        exports = self.queryset[:10]
        return Response(self.get_serializer(exports, many=True).data)



# -----------------------------------------------------------
# 🔥 SALES SUMMARY — PUBLIC  (UPDATED)
# -----------------------------------------------------------
class SalesSummaryView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Sales summary + monthly trend",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("months", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.sales.models import SalesInvoice
        from django.db.models.functions import TruncMonth
        from datetime import timedelta
        from django.utils import timezone

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        location_id = request.query_params.get("location_id")
        months = int(request.query_params.get("months", 6))

        qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)

        # If user manually selected dates → DO NOT use months
        if from_str:
            qs = qs.filter(invoice_date__date__gte=from_str)
        if to_str:
            qs = qs.filter(invoice_date__date__lte=to_str)

        # If dates NOT provided → apply months filter
        if not from_str and not to_str:
            date_from = timezone.now() - timedelta(days=30 * months)
            qs = qs.filter(invoice_date__gte=date_from)

        if location_id:
            qs = qs.filter(location_id=location_id)

        total_revenue = qs.aggregate(s=Sum("net_total")).get("s") or 0
        total_txn = qs.count()
        avg_bill = float(total_revenue) / total_txn if total_txn else 0

        series = (
            qs.annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(total=Sum("net_total"))
            .order_by("m")
        )

        trend = [
            {"month": r["m"].strftime("%Y-%m") if r["m"] else None,
             "total": float(r["total"] or 0)}
            for r in series
        ]

        return Response({
            "total_revenue": float(total_revenue),
            "total_transactions": total_txn,
            "average_bill_value": round(avg_bill, 2),
            "trend": trend,
        })



# -----------------------------------------------------------
# 🔥 PURCHASE SUMMARY — PUBLIC (UPDATED)
# -----------------------------------------------------------
class PurchasesSummaryView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Purchase summary + monthly trend",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("months", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.procurement.models import GoodsReceipt, GoodsReceiptLine
        from django.db.models.functions import TruncMonth
        from django.db.models import Count
        from datetime import timedelta
        from django.utils import timezone

        # Query params
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        location_id = request.query_params.get("location_id")
        months = int(request.query_params.get("months", 10))

        grn_qs = GoodsReceipt.objects.filter(status=GoodsReceipt.Status.POSTED)

        # Apply date range (if user selected)
        if from_str:
            grn_qs = grn_qs.filter(received_at__date__gte=from_str)
        if to_str:
            grn_qs = grn_qs.filter(received_at__date__lte=to_str)

        # If user didn’t apply date-from/to → use "Last X Months"
        if not from_str and not to_str:
            date_from = timezone.now() - timedelta(days=30 * months)
            grn_qs = grn_qs.filter(received_at__gte=date_from)

        if location_id:
            grn_qs = grn_qs.filter(location_id=location_id)

        # Total GRNs
        total_orders = grn_qs.count()

        # Calculate total purchase amount
        lines = GoodsReceiptLine.objects.filter(
            grn_id__in=grn_qs.values_list("id", flat=True)
        )

        total_purchase = sum([
            float((ln.qty_packs_received or 0) * (ln.unit_cost or 0))
            for ln in lines
        ])

        # Monthly trend chart
        series = (
            grn_qs.annotate(m=TruncMonth("received_at"))
            .values("m")
            .annotate(c=Count("id"))
            .order_by("m")
        )

        trend = [
            {
                "month": r["m"].strftime("%Y-%m"),
                "orders": int(r["c"]),
            }
            for r in series
        ]

        return Response({
            "total_purchase": round(total_purchase, 2),
            "total_orders": total_orders,
            "trend": trend,
        })




# -----------------------------------------------------------
# 🔥 EXPIRY REPORT — PUBLIC
# -----------------------------------------------------------
class ExpiryReportView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Expiry tracking table",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter(
                "window",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="warning | critical | all"
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.inventory.services import near_expiry
        from apps.settingsx.services import get_setting
        from apps.catalog.models import Product
        from apps.procurement.models import GoodsReceipt, GoodsReceiptLine
        from datetime import date as _date

        location_id = request.query_params.get("location_id")
        window = request.query_params.get("window") or "all"

        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)

        rows = near_expiry(days=warn_days, location_id=location_id)
        today = _date.today()

        # Get all product objects
        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}

        # Find supplier for each batch
        vendor_by_batch = {}
        grn_lines = GoodsReceiptLine.objects.filter(
            grn__status=GoodsReceipt.Status.POSTED,
            grn__location_id=location_id,
            grn__lines__isnull=False
        ).select_related("grn__po__vendor").order_by("-grn__received_at")

        for gl in grn_lines:
            key = (gl.product_id, gl.batch_no)
            vendor = getattr(getattr(gl.grn.po, "vendor", None), "name", None)
            if key not in vendor_by_batch and vendor:
                vendor_by_batch[key] = vendor

        # Build response
        out = []
        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None

            # Determine status
            if days_left is None:
                status_txt = "Unknown"
            elif days_left <= crit_days:
                status_txt = "Critical"
            elif days_left <= warn_days:
                status_txt = "Warning"
            else:
                status_txt = "Safe"

            # Apply window filter
            if window == "critical" and status_txt != "Critical":
                continue
            if window == "warning" and status_txt != "warning":
                continue

            prod = products.get(r.get("product_id"))
            qty_base = r.get("stock_base") or 0

            # Calculate stock value
            stock_value = None
            if prod and prod.units_per_pack:
                try:
                    price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                    stock_value = round(float(qty_base) * price_per_base, 2)
                except:
                    stock_value = None

            out.append({
                "product_id": r.get("product_id"),
                "product_name": getattr(prod, "name", None),
                "category": getattr(getattr(prod, "category", None), "name", None),
                "batch_lot_id": r.get("batch_lot_id"),
                "batch_no": r.get("batch_no"),
                "expiry_date": exp,
                "days_left": days_left,
                "status": status_txt,
                "quantity": float(qty_base),
                "stock_value": stock_value,
                "supplier": vendor_by_batch.get((r.get("product_id"), r.get("batch_no"))),
            })

        return Response(out)


# -----------------------------------------------------------
# 🔥 EXPIRY SUMMARY — PUBLIC
# -----------------------------------------------------------
class ExpirySummaryView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Expiry KPIs",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.settingsx.services import get_setting
        from apps.catalog.models import Product
        from apps.inventory.services import near_expiry
        from datetime import date as _date

        location_id = request.query_params.get("location_id")

        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)

        rows = near_expiry(days=warn_days, location_id=location_id)
        today = _date.today()

        counts = {"critical": 0, "warning": 0, "safe": 0}
        at_risk_value = 0.0

        # Preload products for pricing
        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}

        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None

            if days_left is None:
                status_txt = "Safe"
            elif days_left <= crit_days:
                status_txt = "Critical"
            elif days_left <= warn_days:
                status_txt = "Warning"
            else:
                status_txt = "Safe"

            # Count items
            counts[status_txt.lower()] += 1

            # Calculate risk value for critical + warning
            if status_txt in ("Critical", "Warning"):
                prod = products.get(r.get("product_id"))
                try:
                    price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                    at_risk_value += float(r.get("stock_base") or 0) * price_per_base
                except:
                    pass

        return Response({
            "critical": counts["critical"],
            "warning": counts["warning"],
            "safe": counts["safe"],
            "at_risk_value": round(at_risk_value, 2),
        })



# -----------------------------------------------------------
# 🔥 TOP SELLING — PUBLIC (UPDATED)
# -----------------------------------------------------------
class TopSellingView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Top selling products",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("months", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.sales.models import SalesInvoice, SalesLine
        from django.db.models import Sum
        from datetime import timedelta
        from django.utils import timezone

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        limit = int(request.query_params.get("limit", 5))
        months = int(request.query_params.get("months", 6))

        inv_qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)

        if from_str:
            inv_qs = inv_qs.filter(invoice_date__date__gte=from_str)
        if to_str:
            inv_qs = inv_qs.filter(invoice_date__date__lte=to_str)

        # ⭐ Default filter — last X months
        if not from_str and not to_str:
            date_from = timezone.now() - timedelta(days=30 * months)
            inv_qs = inv_qs.filter(invoice_date__gte=date_from)

        lines = SalesLine.objects.filter(
            sale_invoice_id__in=inv_qs.values_list("id", flat=True)
        )

        agg = (
            lines.values("product_id", "product__name")
            .annotate(units=Sum("qty_base"), revenue=Sum("line_total"))
            .order_by("-units")[:limit]
        )

        table = [
            {
                "rank": i + 1,
                "medicine_name": r["product__name"],
                "units_sold": float(r["units"] or 0),
                "revenue": float(r["revenue"] or 0),
            }
            for i, r in enumerate(agg)
        ]

        distribution = [
            {"label": r["product__name"], "value": float(r["units"] or 0)}
            for r in agg
        ]

        return Response({"table": table, "distribution": distribution})
