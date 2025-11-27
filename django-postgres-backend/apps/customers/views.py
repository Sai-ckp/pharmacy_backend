from rest_framework import viewsets, filters, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.db.models import Sum, Count
from datetime import date, timedelta
from .models import Customer
from .serializers import CustomerSerializer
from apps.sales.models import SalesInvoice


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("name")
    serializer_class = CustomerSerializer
    permission_classes = [permissions.AllowAny]  # Change later
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "gstin", "code"]
    ordering_fields = ["name", "type", "credit_limit", "outstanding_balance"]

    @extend_schema(
        tags=["Customers"],
        summary="Customers dashboard stats",
        parameters=[
            OpenApiParameter("filter", OpenApiTypes.STR),           # day/week/month
            OpenApiParameter("from", OpenApiTypes.DATE),
            OpenApiParameter("to", OpenApiTypes.DATE),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def list(self, request, *args, **kwargs):

            # --------------------------- DASHBOARD STATS ---------------------------
      if request.query_params.get("stats") == "true":
        

        filtered_by = request.query_params.get("filter")  # day / week / month
        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")

        inv = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)

        today = date.today()

        # --------------------------- PRESET FILTERS ---------------------------
        if filtered_by == "day":
            inv = inv.filter(invoice_date__date=today)

        elif filtered_by == "week":
            week_start = today - timedelta(days=today.weekday())
            inv = inv.filter(invoice_date__date__gte=week_start)

        elif filtered_by == "month":
            month_start = today.replace(day=1)
            inv = inv.filter(invoice_date__date__gte=month_start)

        # --------------------------- CUSTOM DATE RANGE ---------------------------
        if from_str:
            inv = inv.filter(invoice_date__gte=from_str)
        if to_str:
            inv = inv.filter(invoice_date__lte=to_str)

        # --------------------------- CALCULATE KPIs ---------------------------

        # Total customers who have invoices in this filtered period
        filtered_customer_ids = inv.values_list("customer_id", flat=True).distinct()
        total_customers = filtered_customer_ids.count()

        # Revenue and average purchase value
        revenue = inv.aggregate(total=Sum("net_total"))["total"] or 0
        txn = inv.count()
        avg_purchase_value = round((revenue / txn), 2) if txn else 0

        # Active customers = customers who purchased in this filtered period
        active_customers = total_customers

        return Response({
            "total_customers": total_customers,
            "avg_purchase_value": avg_purchase_value,
            "active_customers": active_customers,
            "filter_used": filtered_by or "none",
        })


        # --------------------------- NORMAL LIST ---------------------------
      return super().list(request, *args, **kwargs)


    # --------------------------- CUSTOMER SUMMARY ---------------------------
    @extend_schema(
        tags=["Customers"],
        summary="Customer summary",
        responses={200: OpenApiTypes.OBJECT}
    )
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if request.query_params.get("summary") == "true":
            from apps.sales.models import SalesInvoice

            # All posted invoices for this customer
            inv = SalesInvoice.objects.filter(
                customer_id=instance.id,
                status=SalesInvoice.Status.POSTED
            )

            # ---------- ACTIVE ----------
            total_bills = inv.count()
            is_active = instance.is_active

            # ---------- PURCHASE STATUS ----------
            total_purchases = inv.aggregate(total=Sum("net_total")).get("total") or 0
            avg_bill = float(total_purchases) / total_bills if total_bills else 0

            # ---------- THIS MONTH ----------
            today = date.today()
            month_start = today.replace(day=1)

            month_inv = inv.filter(invoice_date__gte=month_start)

            visits = month_inv.count()
            amount_spent = month_inv.aggregate(s=Sum("net_total")).get("s") or 0

            # ---------- RESPONSE FORMAT ----------
            return Response({
                "customer": CustomerSerializer(instance).data,

                "active": {
                    "is_active": is_active,
                    "total_bills": total_bills,
                },

                "purchase_status": {
                    "total_purchases": float(total_purchases),
                    "avg_bill_value": round(avg_bill, 2),
                },

                "this_month": {
                    "visits": visits,
                    "amount_spent": float(amount_spent),
                }
            })

        return super().retrieve(request, *args, **kwargs)



    # --------------------------- CUSTOMER INVOICES ---------------------------
    @extend_schema(
        tags=["Customers"],
        summary="Customer invoices list (compact)",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="invoices")
    def customer_invoices(self, request, pk=None):
        from apps.sales.models import SalesInvoice

        inv = SalesInvoice.objects.filter(customer_id=pk).order_by("-invoice_date")[:100]

        rows = [{
            "invoice_no": i.invoice_no or i.id,
            "date": i.invoice_date,
            "items": i.lines.count(),
            "amount": i.net_total,
            "payment_status": i.payment_status,
            "id": i.id,
        } for i in inv]

        return Response(rows)
