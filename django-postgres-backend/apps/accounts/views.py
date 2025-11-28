# apps/accounts/views.py

import random
import uuid
from datetime import timedelta
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PasswordResetOTP
from .serializers import (
    OTPRequestSerializer,
    OTPVerifySerializer,
    ResetPasswordSerializer,
    UserCreateSerializer,
    UserListSerializer,
)

User = get_user_model()


# ----------------------------------------------------
# User Create / List
# ----------------------------------------------------
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class UsersListCreateView(APIView):

    def get(self, request):
        users = User.objects.all().order_by("id")
        data = []
        for u in users:
            full_name = f"{u.first_name} {u.last_name}".strip()
            data.append({
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "full_name": full_name,
                "is_active": u.is_active,
                "created_at": u.date_joined,
            })
        return Response(data)

    def post(self, request):
        email = request.data.get("email")
        full_name = request.data.get("full_name", "")
        password = request.data.get("password")
        is_active = request.data.get("is_active", True)

        # --- split full_name ---
        parts = full_name.split()
        first_name = parts[0] if len(parts) > 0 else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # --- username must be UNIQUE and not null ---
        username = email

        # --- create user ---
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
        )

        return Response({"message": "User created"}, status=status.HTTP_201_CREATED)


# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})


# ----------------------------------------------------
# STEP 1: SEND OTP
# ----------------------------------------------------
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()

        # privacy
        if not user:
            return Response({"detail": "OTP sent if email exists."}, status=200)

        otp = f"{random.randint(100000, 999999)}"

        PasswordResetOTP.objects.create(
            email=email,
            otp=otp,
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        send_mail(
            subject="Your OTP for Password Reset",
            message=f"Your OTP is {otp}. It expires in 10 minutes.",
            from_email="saishashank0143@gmail.com",
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({"detail": "OTP sent to email."}, status=200)


# ----------------------------------------------------
# STEP 2: VERIFY OTP
# ----------------------------------------------------
class VerifyOTPView(APIView):   # <-- THIS FIXES YOUR IMPORT ERROR
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        otp_record = PasswordResetOTP.objects.filter(
            email=email,
            otp=otp,
            is_used=False
        ).order_by("-created_at").first()

        if not otp_record:
            return Response({"detail": "Invalid OTP."}, status=400)

        if otp_record.is_expired():
            return Response({"detail": "OTP expired."}, status=400)

        otp_record.is_used = True
        otp_record.save()

        uid = urlsafe_base64_encode(force_bytes(email))
        token = uuid.uuid4().hex

        return Response({"detail": "OTP verified.", "uid": uid, "token": token})


# ----------------------------------------------------
# STEP 3: RESET PASSWORD
# ----------------------------------------------------
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uidb64 = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            email = force_str(urlsafe_base64_decode(uidb64))
        except:
            return Response({"detail": "Invalid UID."}, status=400)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "User not found."}, status=400)

        user.set_password(new_password)
        user.save()

        return Response({"detail": "Password updated successfully."})


# ----------------------------------------------------
# LOGOUT
# ----------------------------------------------------
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "refresh token required."}, status=400)

        try:
            RefreshToken(refresh).blacklist()
        except:
            return Response({"detail": "Invalid refresh token."}, status=400)

        return Response({"detail": "Logged out."})
