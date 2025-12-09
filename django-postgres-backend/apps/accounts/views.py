import random
import hashlib
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth import authenticate, get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from core.models import get_current_license
from .models import PasswordResetOTP, UserDevice
from .serializers import (
    OTPRequestSerializer,
    OTPVerifySerializer,
    ResetPasswordSerializer,
    UserCreateSerializer,
    UserListSerializer,
    LoginSerializer,
)

User = get_user_model()

# ----- helpers ----------------------------------------------------------------

def _generate_numeric_otp(length: int = 6) -> str:
    """Returned a numeric OTP string, zero-padded."""
    return str(random.randint(0, 10**length - 1)).zfill(length)


def _hash_otp(otp: str, salt: str = "") -> str:
    """Returned a hex sha256 hash of otp + salt."""
    h = hashlib.sha256()
    if salt:  # Used salt to separate OTPs (email was a good salt)
        h.update(salt.encode("utf-8"))
    h.update(otp.encode("utf-8"))
    return h.hexdigest()


def _send_otp_email(email: str, otp: str, minutes_valid: int = 15):
    """Sent an OTP email and raised an exception if sending failed."""
    subject = "Your password reset code"
    message = (
        f"Your one-time password (OTP) for password reset was: {otp}\n\n"
        f"This code was valid for {minutes_valid} minutes.\n\n"
        "If you did not request this, please ignore this email."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER)
    send_mail(subject, message, from_email, [email], fail_silently=False)


class LoginView(APIView):
    permission_classes = [AllowAny]
    inactive_license_message = (
        "Your license has expired or is inactive. Please contact support@ckpsoftware.com to renew your license."
    )

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # accept either username or email for login (admin-created users often sign in with email)
        identifier = serializer.validated_data["username"].strip()
        password = serializer.validated_data["password"]
        device_id = serializer.validated_data["device_id"]

        user_obj = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if not user_obj:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)

        user = authenticate(request=request, username=user_obj.get_username(), password=password)
        if not user:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)

        license_obj = get_current_license()
        if not license_obj or not license_obj.is_active:
            return Response({"detail": self.inactive_license_message}, status=status.HTTP_403_FORBIDDEN)

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        device, created = UserDevice.objects.get_or_create(
            user=user,
            defaults={"device_id": device_id, "user_agent": user_agent},
        )

        if not created and device.device_id != device_id:
            return Response(
                {
                    "detail": "This account is already registered on another device. To change your device, please contact support@ckpsoftware.com."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if created:
            device.device_id = device_id
        device.user_agent = user_agent
        device.save(update_fields=["device_id", "user_agent", "last_login_at"])

        refresh = RefreshToken.for_user(user)
        payload = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {"id": user.id, "username": user.get_username()},
            "license": {
                "days_left": license_obj.days_left,
                "valid_to": license_obj.valid_to.isoformat(),
            },
        }
        return Response(payload, status=status.HTTP_200_OK)

# ----- User list / create -----------------------------------------------------

class UsersListCreateView(APIView):
    permission_classes = [AllowAny]  # could have been adjusted to IsAuthenticated

    def get(self, request):
        """Returned a list of users from the auth user table."""
        users = User.objects.all().order_by("id")
        data = []

        for u in users:
            # derived full name
            first = getattr(u, "first_name", "") or ""
            last = getattr(u, "last_name", "") or ""
            full_name = f"{first} {last}".strip() or getattr(u, "full_name", "") or ""

            data.append(
                {
                    "id": u.id,
                    "username": getattr(u, "username", "") or getattr(u, "email", ""),
                    "email": getattr(u, "email", "") or "",
                    "full_name": full_name,
                    "is_active": getattr(u, "is_active", False),
                    "created_at": getattr(u, "date_joined", None),
                }
            )

        return Response(data)

    def post(self, request):
        """Created an auth user (wrote to auth_user)."""
        email = request.data.get("email")
        password = request.data.get("password")
        full_name = request.data.get("full_name", "") or ""
        is_active = request.data.get("is_active", True)

        if not email or not password:
            return Response(
                {"detail": "email and password were required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # username had to be unique – email was used as username
        username = email

        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=username).exists():
            return Response({"detail": "Email already existed."}, status=status.HTTP_400_BAD_REQUEST)

        parts = full_name.strip().split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # create_user hashed the password and set required fields
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
        )

        out = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "is_active": user.is_active,
            "created_at": getattr(user, "date_joined", None),
        }

        return Response(out, status=status.HTTP_201_CREATED)

# ----- Health -----------------------------------------------------------------

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})

# ----- Forgot password (send OTP) ---------------------------------------------

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    OTP_LENGTH = 6
    OTP_VALID_MINUTES = 15

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()

        # found user (abort if account missing)
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response(
                {"detail": "No account exists for this email."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # generated OTP and hashed OTP for DB
        otp = _generate_numeric_otp(self.OTP_LENGTH)
        otp_hash = _hash_otp(otp, salt=email)
        now = timezone.now()

        # created PasswordResetOTP entry
        otp_kwargs = {
            "email": email,
            "otp_hash": otp_hash,
            "created_at": now,
            "is_used": False,
        }

        otp_kwargs["user"] = user

        PasswordResetOTP.objects.create(**otp_kwargs)

        # sent OTP email, deleted row if sending failed
        try:
            _send_otp_email(email, otp, minutes_valid=self.OTP_VALID_MINUTES)
        except Exception as exc:
            PasswordResetOTP.objects.filter(email=email, otp_hash=otp_hash).delete()
            return Response(
                {"detail": "Failed to send OTP email.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # deterministic response when OTP was sent
        resp = {
            "detail": "OTP sent to the registered email address.",
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        }

        return Response(resp, status=status.HTTP_200_OK)

# ----- Verify OTP -------------------------------------------------------------

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    OTP_VALID_MINUTES = 15

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        otp = serializer.validated_data["otp"].strip()

        if not otp or not email:
            return Response(
                {"detail": "email and otp were required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp_hash = _hash_otp(otp, salt=email)

        # found most recent unused OTP
        otp_record = PasswordResetOTP.objects.filter(
            email__iexact=email, is_used=False
        ).order_by("-created_at").first()

        if not otp_record:
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # checked expiry
        if otp_record.created_at + timedelta(minutes=self.OTP_VALID_MINUTES) < timezone.now():
            return Response({"detail": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)

        # matched hash
        if otp_record.otp_hash != otp_hash:
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # marked used
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        # returned uid
        user = User.objects.filter(email__iexact=email).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
        else:
            uid = urlsafe_base64_encode(force_bytes(email))

        return Response(
            {"detail": "OTP had been verified.", "uid": uid, "token": ""},
            status=status.HTTP_200_OK,
        )

# ----- Reset password ---------------------------------------------------------

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Expected payload:
        { uid, token (optional), new_password }

        uid could have been base64-encoded email OR user.pk.
        token:null was normalized to empty string.
        """
        data = {k: v for k, v in request.data.items()}
        if data.get("token", None) is None:
            data["token"] = ""

        serializer = ResetPasswordSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        uidb64 = serializer.validated_data["uid"]
        new_password = serializer.validated_data["new_password"]

        try:
            decoded = force_str(urlsafe_base64_decode(uidb64))
        except Exception:
            return Response({"detail": "Invalid UID."}, status=status.HTTP_400_BAD_REQUEST)

        decoded_clean = decoded.strip()
        decoded_lower = decoded_clean.lower()

        user = None

        # interpreted as pk
        if decoded_clean.isdigit():
            try:
                user = User.objects.filter(pk=int(decoded_clean)).first()
            except Exception:
                user = None

        # interpreted as email
        if not user and "@" in decoded_lower:
            user = User.objects.filter(email__iexact=decoded_lower).first()

        if not user:
            return Response({"detail": "User was not found."}, status=status.HTTP_400_BAD_REQUEST)

        # set new password
        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response(
            {"detail": "Password had been updated successfully."},
            status=status.HTTP_200_OK,
        )

# ----- Logout -----------------------------------------------------------------

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")

        if not refresh:
            return Response(
                {"detail": "refresh token was required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            RefreshToken(refresh).blacklist()
        except Exception:
            return Response(
                {"detail": "Invalid refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)
