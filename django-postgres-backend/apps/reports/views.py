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


class ReportExportViewSet(viewsets.ModelViewSet):
    queryset = ReportExport.objects.all().order_by("-created_at")
    serializer_class = ReportExportSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Override create so export file is generated and
        returned immediately as a download.
        """
        # Create DB entry as usual
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        export = serializer.save(
            status=ReportExport.Status.QUEUED,
            started_at=timezone.now(),
        )
        export.status = ReportExport.Status.RUNNING
        export.save(update_fields=["status", "started_at"])

        try:
            # 🔥 Generate Excel file
            file_path = services.generate_report_file(export)

            export.file_path = file_path
            export.status = ReportExport.Status.DONE
            export.finished_at = timezone.now()
            export.save(update_fields=["status", "file_path", "finished_at"])

            # Full file path
            abs_path = os.path.join(settings.MEDIA_ROOT, file_path)
            if not os.path.exists(abs_path):
                raise FileNotFoundError("Export file missing")

            # 🔥 Return file as a download
            file_handle = open(abs_path, "rb")
            response = FileResponse(
                file_handle,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{os.path.basename(file_path)}"'
            )
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
# 🔥 SALES SUMMARY — PUBLIC
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

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        location_id = request.query_params.get("location_id")
        months = int(request.query_params.get("months", 6))

        qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)

        if from_str:
            qs = qs.filter(invoice_date__date__gte=from_str)
        if to_str:
            qs = qs.filter(invoice_date__date__lte=to_str)
        if location_id:
            qs = qs.filter(location_id=location_id)

        total_revenue = qs.aggregate(s=Sum("net_total")).get("s") or 0
        total_txn = qs.count()
        avg_bill = float(total_revenue) / total_txn if total_txn else 0

        # Monthly trend
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
        ][-months:]

        return Response({
            "total_revenue": float(total_revenue),
            "total_transactions": total_txn,
            "average_bill_value": round(avg_bill, 2),
            "trend": trend,
        })


# -----------------------------------------------------------
# 🔥 PURCHASE SUMMARY — PUBLIC
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

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        location_id = request.query_params.get("location_id")
        months = int(request.query_params.get("months", 10))

        grn_qs = GoodsReceipt.objects.filter(status=GoodsReceipt.Status.POSTED)

        if from_str:
            grn_qs = grn_qs.filter(received_at__date__gte=from_str)
        if to_str:
            grn_qs = grn_qs.filter(received_at__date__lte=to_str)
        if location_id:
            grn_qs = grn_qs.filter(location_id=location_id)

        total_orders = grn_qs.count()

        lines = GoodsReceiptLine.objects.filter(grn_id__in=grn_qs.values_list("id", flat=True))

        total_purchase = sum([
            float((ln.qty_packs_received or 0) * (ln.unit_cost or 0)) for ln in lines
        ])

        series = (
            grn_qs.annotate(m=TruncMonth("received_at"))
            .values("m")
            .annotate(c=Count("id"))
            .order_by("m")
        )

        trend = [
            {"month": r["m"].strftime("%Y-%m") if r["m"] else None,
             "orders": int(r["c"])}
            for r in series
        ][-months:]

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
            OpenApiParameter("window", OpenApiTypes.STR,
                             OpenApiParameter.QUERY, description="warning|critical|all"),
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

        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}

        vendor_by_batch = {}
        for gl in GoodsReceiptLine.objects.filter(
            grn__status=GoodsReceipt.Status.POSTED,
            grn__location_id=location_id,
            grn__lines__isnull=False
        ).select_related('grn__po__vendor').order_by('-grn__received_at'):

            key = (gl.product_id, gl.batch_no)
            if key not in vendor_by_batch and gl.grn and gl.grn.po and gl.grn.po.vendor:
                vendor_by_batch[key] = gl.grn.po.vendor.name

        out = []
        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None

            status_txt = "Safe"
            if days_left is not None:
                if days_left <= crit_days:
                    status_txt = "Critical"
                elif days_left <= warn_days:
                    status_txt = "Warning"

            prod = products.get(r.get("product_id"))

            qty_base = r.get("stock_base") or 0
            stock_value = None

            if prod and prod.units_per_pack and prod.units_per_pack != 0:
                try:
                    price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                    stock_value = round(float(qty_base) * price_per_base, 2)
                except:
                    stock_value = None

            item = {
                "product_id": r.get("product_id"),
                "product_name": getattr(prod, 'name', None),
                "category": getattr(getattr(prod, 'category', None), 'name', None),
                "batch_lot_id": r.get("batch_lot_id"),
                "batch_no": r.get("batch_no"),
                "expiry_date": exp,
                "days_left": days_left,
                "status": status_txt,
                "quantity": float(qty_base),
                "stock_value": stock_value,
                "supplier": vendor_by_batch.get((r.get("product_id"), r.get("batch_no"))),
            }

            if window == "critical" and status_txt != "Critical":
                continue
            if window == "warning" and status_txt == "Safe":
                continue

            out.append(item)

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

        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}

        today = _date.today()

        counts = {"critical": 0, "warning": 0, "safe": 0}
        at_risk_value = 0.0

        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None

            status_txt = "Safe"
            if days_left is not None:
                if days_left <= crit_days:
                    status_txt = "Critical"
                elif days_left <= warn_days:
                    status_txt = "Warning"

            counts[status_txt.lower()] += 1

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
# 🔥 TOP SELLING — PUBLIC
# -----------------------------------------------------------
class TopSellingView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["Reports"],
        summary="Top selling products",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        from apps.sales.models import SalesInvoice, SalesLine
        from django.db.models import Sum

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")
        limit = int(request.query_params.get("limit", 5))

        inv_qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)

        if from_str:
            inv_qs = inv_qs.filter(invoice_date__date__gte=from_str)
        if to_str:
            inv_qs = inv_qs.filter(invoice_date__date__lte=to_str)

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
