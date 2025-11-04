from rest_framework import serializers


class OkSerializer(serializers.Serializer):
    ok = serializers.BooleanField()

