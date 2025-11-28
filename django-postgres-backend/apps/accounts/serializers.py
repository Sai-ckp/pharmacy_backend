# apps/accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


# -----------------------------
# OK Serializer
# -----------------------------
class OkSerializer(serializers.Serializer):
    ok = serializers.BooleanField()


# -----------------------------
# FORGOT PASSWORD — OTP REQUEST
# -----------------------------
class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

# -----------------------------
# OTP VERIFY
# -----------------------------
class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)


# -----------------------------
# RESET PASSWORD
# -----------------------------

class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=6)



class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=4, max_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


# -----------------------------
# USER LIST + CREATE USER API
# -----------------------------
class UserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=6)
    is_active = serializers.BooleanField(default=True)


class UserListSerializer(serializers.ModelSerializer):
    userId = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "userId", "email", "full_name", "is_active", "created_at")

    def get_userId(self, obj):
        return f"USR{obj.pk:03d}"
