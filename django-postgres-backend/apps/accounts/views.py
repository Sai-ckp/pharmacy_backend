import random
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordResetOTP
from .serializers import (
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    VerifyOtpSerializer,
)


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "If an account exists for this email, an OTP has been sent."})
        PasswordResetOTP.objects.filter(email__iexact=email, is_used=False).update(is_used=True)
        otp = f"{random.randint(0, 999999):06d}"
        PasswordResetOTP.objects.create(email=email, otp_hash=make_password(otp))
        send_mail(
            subject="Password reset OTP",
            message=f"Hi {user.get_full_name() or user.username}, your OTP is {otp}. It expires in 10 minutes.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[email],
        )
        return Response({"detail": "OTP sent if the account exists."})


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]
        record = (
            PasswordResetOTP.objects.filter(email__iexact=email, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not record or record.is_expired():
            return Response({"detail": "OTP expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)
        if not check_password(otp, record.otp_hash):
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)
        record.is_used = True
        record.save(update_fields=["is_used"])
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return Response({"uid": uid, "token": token})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uidb64 = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({"detail": "Invalid reset token."}, status=status.HTTP_400_BAD_REQUEST)
        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out."})

