from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ("status", "created_at", "sent_at", "error")

    def create(self, validated_data):
        validated_data["status"] = Notification.Status.QUEUED
        return super().create(validated_data)
