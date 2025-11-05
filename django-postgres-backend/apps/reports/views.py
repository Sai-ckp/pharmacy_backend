from rest_framework import viewsets, permissions
from .models import ReportExport
from .serializers import ReportExportSerializer

class ReportExportViewSet(viewsets.ModelViewSet):
    queryset = ReportExport.objects.all().order_by("-created_at")
    serializer_class = ReportExportSerializer
    permission_classes = [permissions.IsAuthenticated]
