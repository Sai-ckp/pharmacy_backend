from rest_framework import serializers
from .models import ReportExport

class ReportExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField() 
    class Meta:
        model = ReportExport
        fields = "__all__"
        read_only_fields = ("status", "started_at", "finished_at", "file_path", "created_at")

    def create(self, validated_data):
        validated_data["status"] = ReportExport.Status.QUEUED
        return super().create(validated_data)
    
    def get_download_url(self, obj):
        if not obj.file_path:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(f"/media/{obj.file_path}")
