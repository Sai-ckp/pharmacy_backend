from rest_framework import viewsets, permissions, status
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

    def perform_create(self, serializer):
        export = serializer.save(status=ReportExport.Status.QUEUED)
        try:
            export.started_at = timezone.now()
            export.status = ReportExport.Status.RUNNING
            export.save(update_fields=["status", "started_at"])
            services.generate_report_file(export)
            export.status = ReportExport.Status.DONE
            export.finished_at = timezone.now()
        except Exception as e:
            export.status = ReportExport.Status.FAILED
            export.file_path = str(e)
        export.save(update_fields=["status", "finished_at", "file_path"])

    @action(detail=False, methods=["get"], url_path="recent")
    def recent_exports(self, request):
        """Return last 10 generated reports."""
        exports = self.queryset[:10]
        return Response(self.get_serializer(exports, many=True).data, status=status.HTTP_200_OK)


class SalesSummaryView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

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
    def list(self, request):
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
        # trend by month
        series = (
            qs.annotate(m=TruncMonth("invoice_date"))
            .values("m")
            .annotate(total=Sum("net_total"))
            .order_by("m")
        )
        trend = [{"month": r["m"].strftime("%Y-%m") if r["m"] else None, "total": float(r["total"] or 0)} for r in series][-months:]
        return Response({
            "total_revenue": float(total_revenue),
            "total_transactions": total_txn,
            "average_bill_value": round(avg_bill, 2),
            "trend": trend,
        })


class PurchasesSummaryView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

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
    def list(self, request):
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
        # sum value of lines qty_packs_received * unit_cost
        lines = GoodsReceiptLine.objects.filter(grn_id__in=grn_qs.values_list("id", flat=True))
        total_purchase = sum([
            float((ln.qty_packs_received or 0) * (ln.unit_cost or 0)) for ln in lines
        ])
        # monthly trend
        series = (
            grn_qs.annotate(m=TruncMonth("received_at"))
            .values("m")
            .annotate(c=Count("id"))
            .order_by("m")
        )
        trend = [{"month": r["m"].strftime("%Y-%m") if r["m"] else None, "orders": int(r["c"]) } for r in series][-months:]
        return Response({
            "total_purchase": round(total_purchase, 2),
            "total_orders": total_orders,
            "trend": trend,
        })


class ExpiryReportView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Reports"],
        summary="Expiry tracking table",
        parameters=[
            OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("window", OpenApiTypes.STR, OpenApiParameter.QUERY, description="warning|critical|all"),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        from apps.inventory.services import near_expiry
        from apps.settingsx.services import get_setting
        from apps.catalog.models import Product
        from apps.procurement.models import GoodsReceipt, GoodsReceiptLine
        location_id = request.query_params.get("location_id")
        window = request.query_params.get("window") or "all"
        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
        # For table we list all items within warning window
        rows = near_expiry(days=warn_days, location_id=location_id)
        out = []
        from datetime import date as _date
        today = _date.today()
        # Preload product data
        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}
        # Vendor lookup by last GRN for batch
        batch_ids = [r.get("batch_lot_id") for r in rows]
        last_grn = (
            GoodsReceiptLine.objects.filter(grn__status=GoodsReceipt.Status.POSTED, grn__location_id=location_id, grn__lines__isnull=False, grn__id=GoodsReceiptLine.objects.filter(batch_no__isnull=False).values('grn'))
        )
        # Simple vendor mapping: latest GRN per batch
        vendor_by_batch = {}
        for gl in GoodsReceiptLine.objects.filter(grn__status=GoodsReceipt.Status.POSTED, grn__location_id=location_id, grn__lines__isnull=False).select_related('grn__po__vendor').order_by('-grn__received_at'):
            key = (gl.product_id, gl.batch_no)
            if key not in vendor_by_batch and gl.grn and gl.grn.po and gl.grn.po.vendor:
                vendor_by_batch[key] = gl.grn.po.vendor.name
        for r in rows:
            exp = r.get("expiry_date")
            days_left = (exp - today).days if exp else None
            status_txt = "Safe"
            if days_left is not None:
                if days_left <= crit_days:
                    status_txt = "Critical"
                elif days_left <= warn_days:
                    status_txt = "Warning"
            pid = r.get("product_id")
            prod = products.get(pid)
            qty_base = r.get("stock_base") or 0
            stock_value = None
            if prod and prod.units_per_pack and prod.units_per_pack != 0:
                try:
                    price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                    stock_value = round(float(qty_base) * price_per_base, 2)
                except Exception:
                    stock_value = None
            supplier = vendor_by_batch.get((pid, r.get("batch_no")))
            item = {
                "product_id": pid,
                "product_name": getattr(prod, 'name', None),
                "category": getattr(getattr(prod, 'category', None), 'name', None),
                "batch_lot_id": r.get("batch_lot_id"),
                "batch_no": r.get("batch_no"),
                "expiry_date": exp,
                "days_left": days_left,
                "status": status_txt,
                "quantity": float(qty_base),
                "stock_value": stock_value,
                "supplier": supplier,
            }
            if window == "critical" and status_txt != "Critical":
                continue
            if window == "warning" and status_txt == "Safe":
                continue
            out.append(item)
        return Response(out)


class ExpirySummaryView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Reports"],
        summary="Expiry KPIs (critical/warning/safe + at-risk value)",
        parameters=[OpenApiParameter("location_id", OpenApiTypes.INT, OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
        from apps.settingsx.services import get_setting
        from apps.catalog.models import Product
        from apps.inventory.services import near_expiry
        location_id = request.query_params.get("location_id")
        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
        rows = near_expiry(days=warn_days, location_id=location_id)
        # preload products
        pids = list({r.get("product_id") for r in rows})
        products = {p.id: p for p in Product.objects.filter(id__in=pids)}
        from datetime import date as _date
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
            # stock value for critical+warning
            if status_txt in ("Critical", "Warning"):
                prod = products.get(r.get("product_id"))
                try:
                    price_per_base = float(prod.mrp) / float(prod.units_per_pack)
                    at_risk_value += (float(r.get("stock_base") or 0) * price_per_base)
                except Exception:
                    pass
        return Response({
            "critical": counts["critical"],
            "warning": counts["warning"],
            "safe": counts["safe"],
            "at_risk_value": round(at_risk_value, 2),
        })


class TopSellingView(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Reports"],
        summary="Top selling products and distribution",
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("to", OpenApiTypes.DATE, OpenApiParameter.QUERY),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request):
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
        lines = SalesLine.objects.filter(sale_invoice_id__in=inv_qs.values_list("id", flat=True))
        agg = (
            lines.values("product_id", "product__name")
            .annotate(units=Sum("qty_base"), revenue=Sum("line_total"))
            .order_by("-units")[:limit]
        )
        table = [{"rank": i+1, "medicine_name": r["product__name"], "units_sold": float(r["units"] or 0), "revenue": float(r["revenue"] or 0)} for i, r in enumerate(agg)]
        # simple distribution series for chart
        distribution = [{"label": r["product__name"], "value": float(r["units"] or 0)} for r in agg]
        return Response({"table": table, "distribution": distribution})
