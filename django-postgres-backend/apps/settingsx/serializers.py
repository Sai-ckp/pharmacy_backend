from rest_framework import serializers
from .models import Settings, BusinessProfile, DocCounter


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = "__all__"


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = "__all__"


class DocCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocCounter
        fields = "__all__"

