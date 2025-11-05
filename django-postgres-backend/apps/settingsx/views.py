from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, viewsets
from .models import Settings, BusinessProfile, DocCounter
from .serializers import SettingsSerializer, BusinessProfileSerializer, DocCounterSerializer


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class SettingsListCreateView(generics.ListCreateAPIView):
    queryset = Settings.objects.all()
    serializer_class = SettingsSerializer


class SettingsDetailView(generics.RetrieveUpdateAPIView):
    lookup_field = "pk"
    queryset = Settings.objects.all()
    serializer_class = SettingsSerializer


class BusinessProfileView(generics.RetrieveUpdateAPIView):
    queryset = BusinessProfile.objects.all()
    serializer_class = BusinessProfileSerializer

    def get_object(self):
        obj, _ = BusinessProfile.objects.get_or_create(id=1)
        return obj


class SettingsGroupView(APIView):
    def get(self, request):
        keys = {
            "alerts": ["expiry_critical_days", "expiry_warning_days", "low_stock_threshold_default", "pending_bill_alert_days"],
            "tax": ["gst_rate_default", "tax_calc_method"],
            "billing": [],
        }
        data = {}
        for group, items in keys.items():
            data[group] = {k: Settings.objects.filter(key=k).values_list("value", flat=True).first() for k in items}
        return Response(data)


class DocCounterViewSet(viewsets.ModelViewSet):
    queryset = DocCounter.objects.all()
    serializer_class = DocCounterSerializer

