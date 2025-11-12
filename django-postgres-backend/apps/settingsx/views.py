from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, viewsets, status
from .models import SettingKV, BusinessProfile, DocCounter
from .serializers import (
    SettingsSerializer, BusinessProfileSerializer, DocCounterSerializer,
    PaymentMethodSerializer, PaymentTermSerializer,
)
from .models import PaymentMethod, PaymentTerm
from rest_framework import viewsets
from . import services
from .services_backup import restore_backup
from apps.governance.permissions import IsAdmin


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class SettingsListCreateView(generics.ListCreateAPIView):
    queryset = SettingKV.objects.all()
    serializer_class = SettingsSerializer


class SettingsDetailView(generics.RetrieveUpdateAPIView):
    lookup_field = "pk"
    queryset = SettingKV.objects.all()
    serializer_class = SettingsSerializer


class BusinessProfileView(generics.RetrieveUpdateAPIView):
    queryset = BusinessProfile.objects.all()
    serializer_class = BusinessProfileSerializer

    def get_object(self):
        obj, _ = BusinessProfile.objects.get_or_create(id=1)
        return obj


class SettingsGroupView(APIView):
    def get(self, request):
        # Grouped read convenience for UI
        keys = {
            "alerts": [
                "ALERT_EXPIRY_CRITICAL_DAYS",
                "ALERT_EXPIRY_WARNING_DAYS",
                "ALERT_LOW_STOCK_DEFAULT",
            ],
            "tax": [
                "TAX_GST_RATE",
                "TAX_CGST_RATE",
                "TAX_SGST_RATE",
                "TAX_CALC_METHOD",
            ],
            "invoice": [
                "INVOICE_PREFIX",
                "INVOICE_START",
                "INVOICE_TEMPLATE",
                "INVOICE_FOOTER",
            ],
            "notifications": [
                "NOTIFY_EMAIL_ENABLED",
                "NOTIFY_LOW_STOCK",
                "NOTIFY_EXPIRY",
                "NOTIFY_DAILY_REPORT",
                "NOTIFY_EMAIL",
                "NOTIFY_SMS_ENABLED",
                "NOTIFY_SMS_PHONE",
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USER",
                "SMTP_PASSWORD",
            ],
        }
        data = {}
        for group, items in keys.items():
            data[group] = {k: SettingKV.objects.filter(key=k).values_list("value", flat=True).first() for k in items}
        return Response(data)


class DocCounterViewSet(viewsets.ModelViewSet):
    queryset = DocCounter.objects.all()
    serializer_class = DocCounterSerializer


class KVDetailView(APIView):
    def get(self, request, key: str):
        val = services.get_setting(key)
        if val is None:
            return Response({"key": key, "value": None}, status=status.HTTP_404_NOT_FOUND)
        return Response({"key": key, "value": val})

    def put(self, request, key: str):
        value = request.data.get("value")
        if value is None:
            return Response({"detail": "value is required"}, status=status.HTTP_400_BAD_REQUEST)
        services.set_setting(key, str(value))
        return Response({"key": key, "value": str(value)})


class DocCounterNextView(APIView):
    def post(self, request):
        document_type = request.data.get("document_type")
        prefix = request.data.get("prefix", "")
        padding = request.data.get("padding")
        if not document_type:
            return Response({"detail": "document_type is required"}, status=status.HTTP_400_BAD_REQUEST)
        pad_int = int(padding) if padding is not None else None
        number = services.next_doc_number(document_type, prefix=prefix or "", padding=pad_int)
        return Response({"number": number})


class BackupRestoreView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        archive_id = request.data.get("archive_id")
        if not archive_id:
            return Response({"detail": "archive_id required"}, status=status.HTTP_400_BAD_REQUEST)
        result = restore_backup(archive_id=int(archive_id), actor=request.user)
        code = result.get("code")
        if code in {"RESTORE_DISABLED", "FORBIDDEN", "INVALID_PATH", "NOT_FOUND"}:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class PaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = PaymentMethod.objects.all()
    serializer_class = PaymentMethodSerializer

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


class PaymentTermViewSet(viewsets.ModelViewSet):
    queryset = PaymentTerm.objects.all()
    serializer_class = PaymentTermSerializer

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

