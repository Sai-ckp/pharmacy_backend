from rest_framework import generics, serializers, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdmin
from .models import AuditLog
from . import services


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"ok": True})


class AuditLogListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    actor_user_id = serializers.IntegerField(allow_null=True)
    action = serializers.CharField()
    table_name = serializers.CharField()
    record_id = serializers.CharField()
    created_at = serializers.DateTimeField()


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogListSerializer

    def get_queryset(self):
        return AuditLog.objects.all()

    def list(self, request, *args, **kwargs):
        qs = AuditLog.objects.all()
        table = request.query_params.get("table")
        record_id = request.query_params.get("record_id")
        if table:
            qs = qs.filter(table_name=table)
        if record_id:
            qs = qs.filter(record_id=str(record_id))
        data = list(
            qs.order_by("-created_at").values(
                "id", "actor_user_id", "action", "table_name", "record_id", "created_at"
            )
        )
        return Response(data)


class RunExpiryScanView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        result = services.run_expiry_scan()
        return Response(result, status=status.HTTP_200_OK)


class RunLowStockScanView(APIView):
    permission_classes = [IsAdmin]
    def post(self, request):
        result = services.run_low_stock_scan()
        return Response({"count": len(result), "items": result}, status=status.HTTP_200_OK)

