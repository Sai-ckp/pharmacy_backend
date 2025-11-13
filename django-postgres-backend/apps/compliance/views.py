from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django_filters.rest_framework import DjangoFilterBackend
from .models import Prescription, H1RegisterEntry, NDPSDailyEntry, RecallEvent
from .serializers import (
    PrescriptionSerializer,
    H1RegisterEntrySerializer,
    NDPSDailyEntrySerializer,
    RecallEventSerializer,
)


class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["post"], url_path="extend-validity")
    def extend_validity(self, request, pk=None):
        pres = self.get_object()
        pres.valid_till = timezone.now().date() + timedelta(days=30)
        pres.save(update_fields=["valid_till"])
        return Response({"valid_till": pres.valid_till})


class H1RegisterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = H1RegisterEntry.objects.all()
    serializer_class = H1RegisterEntrySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["invoice", "product", "batch_lot", "entry_date"]


class NDPSDailyEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NDPSDailyEntry.objects.all()
    serializer_class = NDPSDailyEntrySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["product", "date"]

    @action(detail=False, methods=["post"], url_path="recompute")
    def recompute(self, request):
        """Trigger recomputation of NDPS balances."""
        from .services import recompute_ndps_daily
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        product_id = request.data.get("product_id")
        recompute_ndps_daily(product_id, start_date, end_date)
        return Response({"status": "recomputed"}, status=status.HTTP_200_OK)


class RecallEventViewSet(viewsets.ModelViewSet):
    queryset = RecallEvent.objects.all()
    serializer_class = RecallEventSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["post"], url_path="close")
    def close_recall(self, request, pk=None):
        recall = self.get_object()
        recall.status = "CLOSED"
        recall.save(update_fields=["status"])
        return Response({"status": "closed"})
