from rest_framework import viewsets, permissions
from .models import Prescription, H1RegisterEntry, NDPSDailyEntry, RecallEvent
from .serializers import PrescriptionSerializer, H1RegisterEntrySerializer, NDPSDailyEntrySerializer, RecallEventSerializer

class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = PrescriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

class H1RegisterEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = H1RegisterEntry.objects.all()
    serializer_class = H1RegisterEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

class NDPSDailyEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NDPSDailyEntry.objects.all()
    serializer_class = NDPSDailyEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

class RecallEventViewSet(viewsets.ModelViewSet):
    queryset = RecallEvent.objects.all()
    serializer_class = RecallEventSerializer
    permission_classes = [permissions.IsAuthenticated]
