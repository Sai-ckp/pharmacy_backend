from rest_framework import serializers
<<<<<<< HEAD
=======

>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
from .models import Prescription, H1RegisterEntry, NDPSDailyEntry, RecallEvent

class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = "__all__"
<<<<<<< HEAD
        read_only_fields = ['id', 'created_at', 'updated_at']

=======
        read_only_fields = ("created_at","updated_at")
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a

class H1RegisterEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = H1RegisterEntry
        fields = "__all__"
<<<<<<< HEAD
        read_only_fields = ["id", "entry_date"]

=======
        read_only_fields = fields
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a

class NDPSDailyEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = NDPSDailyEntry
        fields = "__all__"
<<<<<<< HEAD
        read_only_fields = ["id"]
=======
        read_only_fields = fields
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a

class RecallEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecallEvent
        fields = "__all__"
<<<<<<< HEAD
=======


class PrescriptionSerializer(serializers.Serializer):
    pass

>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
