from rest_framework import serializers
from .models import Prescription, H1RegisterEntry, NDPSDailyEntry, RecallEvent

class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = "__all__"
        read_only_fields = ("created_at","updated_at")

class H1RegisterEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = H1RegisterEntry
        fields = "__all__"
        read_only_fields = fields

class NDPSDailyEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = NDPSDailyEntry
        fields = "__all__"
        read_only_fields = fields

class RecallEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecallEvent
        fields = "__all__"
