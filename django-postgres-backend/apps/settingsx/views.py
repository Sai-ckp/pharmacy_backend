from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from .models import Settings, BusinessProfile
from .serializers import SettingsSerializer, BusinessProfileSerializer


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

