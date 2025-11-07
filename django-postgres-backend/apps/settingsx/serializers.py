from rest_framework import serializers
from .models import SettingKV, BusinessProfile, DocCounter


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SettingKV
        fields = "__all__"


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        fields = "__all__"


class DocCounterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocCounter
        fields = "__all__"

