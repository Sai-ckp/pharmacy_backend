from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from .models import ReportExport
from .serializers import ReportExportSerializer
from . import services


class ReportExportViewSet(viewsets.ModelViewSet):
    queryset = ReportExport.objects.all().order_by("-created_at")
    serializer_class = ReportExportSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        export = serializer.save(status=ReportExport.Status.QUEUED)
        try:
            export.started_at = timezone.now()
            export.status = ReportExport.Status.RUNNING
            export.save(update_fields=["status", "started_at"])
            services.generate_report_file(export)
            export.status = ReportExport.Status.DONE
            export.finished_at = timezone.now()
        except Exception as e:
            export.status = ReportExport.Status.FAILED
            export.file_path = str(e)
        export.save(update_fields=["status", "finished_at", "file_path"])

    @action(detail=False, methods=["get"], url_path="recent")
    def recent_exports(self, request):
        """Return last 10 generated reports."""
        exports = self.queryset[:10]
        return Response(self.get_serializer(exports, many=True).data, status=status.HTTP_200_OK)
