from rest_framework import serializers
from .models import ReportExport

class ReportExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportExport
        fields = "__all__"
        read_only_fields = ("status","started_at","finished_at","file_path","created_at")

    def create(self, validated_data):
        validated_data["status"] = "QUEUED"
        return super().create(validated_data)
