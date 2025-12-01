from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, viewsets, status, permissions
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter, OpenApiTypes
from .models import SettingKV, BusinessProfile, DocCounter
from .serializers import (
    SettingsSerializer, BusinessProfileSerializer, DocCounterSerializer,
    PaymentMethodSerializer, PaymentTermSerializer, NotificationSettingsSerializer, TaxBillingSettingsSerializer, AlertThresholdsSerializer,
)
from .models import PaymentMethod, PaymentTerm, NotificationSettings, TaxBillingSettings, AlertThresholds
from rest_framework import viewsets
from . import services
from .services_backup import restore_backup, create_backup
from apps.governance.permissions import IsAdmin


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

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
    @extend_schema(
        tags=["Settings"],
        summary="Get grouped application settings",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        # Grouped read convenience for UI
        keys = {
            "alerts": [
                "ALERT_EXPIRY_CRITICAL_DAYS",
                "ALERT_EXPIRY_WARNING_DAYS",
                "ALERT_LOW_STOCK_DEFAULT",
                "ALERT_CHECK_FREQUENCY",
                "AUTO_REMOVE_EXPIRED",
                "OUT_OF_STOCK_ACTION",
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
            "backups": [
                "AUTO_BACKUP_ENABLED",
                "AUTO_BACKUP_FREQUENCY",
                "AUTO_BACKUP_TIME",
            ],
        }
        data = {}
        for group, items in keys.items():
            data[group] = {k: SettingKV.objects.filter(key=k).values_list("value", flat=True).first() for k in items}
        return Response(data)


class SettingsGroupSaveView(APIView):
    @extend_schema(
        tags=["Settings"],
        summary="Batch save grouped settings (alerts/tax/invoice/notifications/backups)",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Tax & Invoice Save",
                value={
                    "tax": {
                        "TAX_GST_RATE": "12",
                        "TAX_CGST_RATE": "6",
                        "TAX_SGST_RATE": "6",
                        "TAX_CALC_METHOD": "INCLUSIVE",
                    },
                    "invoice": {
                        "INVOICE_PREFIX": "INV-",
                        "INVOICE_START": "1001",
                        "INVOICE_TEMPLATE": "STANDARD",
                        "INVOICE_FOOTER": "Thank you",
                    },
                },
            )
        ],
    )
    def post(self, request):
        # Accept nested dict of {group: {KEY: value}}
        payload = request.data or {}
        to_write: dict[str, str] = {}
        for group, kvs in payload.items():
            if not isinstance(kvs, dict):
                continue
            for k, v in kvs.items():
                if v is None:
                    continue
                to_write[str(k)] = str(v)
        if not to_write:
            return Response({"updated": 0})
        from django.db import transaction
        from .services import set_setting, get_setting
        from apps.governance.services import audit
        with transaction.atomic():
            for k, v in to_write.items():
                before = get_setting(k)
                set_setting(k, v)
                audit(
                    request.user if request.user.is_authenticated else None,
                    table="settings_kv",
                    row_id=hash(k) % 2**31,
                    action="UPSERT",
                    before={"key": k, "value": before},
                    after={"key": k, "value": v},
                )
        return self.get(request)


class DocCounterViewSet(viewsets.ModelViewSet):
    queryset = DocCounter.objects.all()
    serializer_class = DocCounterSerializer


class NotificationSettingsView(APIView):
    @extend_schema(tags=["Settings"], summary="Get notification settings", responses={200: NotificationSettingsSerializer})
    def get(self, request):
        obj, _ = NotificationSettings.objects.get_or_create(id=1)
        return Response(NotificationSettingsSerializer(obj).data)

    @extend_schema(tags=["Settings"], summary="Update notification settings", request=NotificationSettingsSerializer, responses={200: NotificationSettingsSerializer})
    def put(self, request):
        obj, _ = NotificationSettings.objects.get_or_create(id=1)
        ser = NotificationSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class TaxBillingSettingsView(APIView):
    @extend_schema(tags=["Settings"], summary="Get tax & billing settings", responses={200: TaxBillingSettingsSerializer})
    def get(self, request):
        obj, _ = TaxBillingSettings.objects.get_or_create(id=1)
        return Response(TaxBillingSettingsSerializer(obj).data)

    @extend_schema(tags=["Settings"], summary="Update tax & billing settings", request=TaxBillingSettingsSerializer, responses={200: TaxBillingSettingsSerializer})
    def put(self, request):
        obj, _ = TaxBillingSettings.objects.get_or_create(id=1)
        ser = TaxBillingSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class AlertThresholdsView(APIView):
    @extend_schema(tags=["Settings"], summary="Get alert thresholds", responses={200: AlertThresholdsSerializer})
    def get(self, request):
        obj, _ = AlertThresholds.objects.get_or_create(id=1)
        return Response(AlertThresholdsSerializer(obj).data)

    @extend_schema(tags=["Settings"], summary="Update alert thresholds", request=AlertThresholdsSerializer, responses={200: AlertThresholdsSerializer})
    def put(self, request):
        obj, _ = AlertThresholds.objects.get_or_create(id=1)
        ser = AlertThresholdsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class NotificationTestView(APIView):
    @extend_schema(tags=["Settings"], summary="Test SMTP connection", responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        settings_obj, _ = NotificationSettings.objects.get_or_create(id=1)
        # Minimal stub: return success if host/port set
        ok = bool(settings_obj.smtp_host and settings_obj.smtp_port)
        return Response({"ok": ok, "host": settings_obj.smtp_host, "port": settings_obj.smtp_port})


class KVDetailView(APIView):
    @extend_schema(
        tags=["Settings"],
        summary="Read a single setting by key",
        parameters=[OpenApiParameter(name="key", type=str, location=OpenApiParameter.PATH)],
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, key: str):
        val = services.get_setting(key)
        if val is None:
            return Response({"key": key, "value": None}, status=status.HTTP_404_NOT_FOUND)
        return Response({"key": key, "value": val})

    @extend_schema(
        tags=["Settings"],
        summary="Upsert a single setting by key",
        parameters=[OpenApiParameter(name="key", type=str, location=OpenApiParameter.PATH)],
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("Set GST", value={"value": "12"})],
    )
    def put(self, request, key: str):
        value = request.data.get("value")
        if value is None:
            return Response({"detail": "value is required"}, status=status.HTTP_400_BAD_REQUEST)
        services.set_setting(key, str(value))
        return Response({"key": key, "value": str(value)})


class DocCounterNextView(APIView):
    @extend_schema(
        tags=["Settings"],
        summary="Get next formatted document number",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample("Next PO Number", value={"document_type": "PO", "prefix": "PO-", "padding": 5})
        ],
    )
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
    @extend_schema(
        tags=["Settings"],
        summary="Restore database from a backup archive (Admin)",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        examples=[OpenApiExample("Restore", value={"archive_id": 7})],
    )
    def post(self, request):
        archive_id = request.data.get("archive_id")
        if not archive_id:
            return Response({"detail": "archive_id required"}, status=status.HTTP_400_BAD_REQUEST)
        result = restore_backup(archive_id=int(archive_id), actor=request.user)
        code = result.get("code")
        if code in {"RESTORE_DISABLED", "FORBIDDEN", "INVALID_PATH", "NOT_FOUND"}:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class BackupCreateView(APIView):
    permission_classes = [IsAdmin]
    @extend_schema(
        tags=["Settings"],
        summary="Create a full backup archive (Admin)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        result = create_backup(actor=request.user)
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

