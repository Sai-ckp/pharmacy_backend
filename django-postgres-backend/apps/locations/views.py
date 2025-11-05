from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from .models import Location
from .serializers import LocationSerializer


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

