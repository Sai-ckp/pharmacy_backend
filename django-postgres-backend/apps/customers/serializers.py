from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
<<<<<<< HEAD

=======
        
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
<<<<<<< HEAD
        read_only_fields = ('id',)
=======
        read_only_fields = ('id',)
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
