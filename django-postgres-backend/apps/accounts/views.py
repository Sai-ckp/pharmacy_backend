# apps/accounts/views.py
import random
import hashlib
from datetime import timedelta

from django.conf import settings
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


# ----- helpers ----------------------------------------------------------------
def _generate_numeric_otp(length: int = 6) -> str:
    """Return numeric OTP string, zero-padded."""
    return str(random.randint(0, 10**length - 1)).zfill(length)


def _hash_otp(otp: str, salt: str = "") -> str:
    """Return hex sha256 hash of otp + salt."""
    h = hashlib.sha256()
    if salt:
        # Use salt to separate OTPs (email is a good salt)
        h.update(salt.encode("utf-8"))
    h.update(otp.encode("utf-8"))
    return h.hexdigest()


def _send_otp_email(email: str, otp: str, minutes_valid: int = 15):
    """Send OTP email. Raises exception if send fails."""
    subject = "Your password reset code"
    message = (
        f"Your one-time password (OTP) for password reset is: {otp}\n\n"
        f"This code is valid for {minutes_valid} minutes.\n\n"
        "If you did not request this, please ignore this email."
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER)
    send_mail(subject, message, from_email, [email], fail_silently=False)


# ----- User list / create -----------------------------------------------------
class UsersListCreateView(APIView):
    permission_classes = [AllowAny]  # adjust to IsAuthenticated if needed

    def get(self, request):
        """
        Return list of users from the auth user table.
        Fields: id, username, email, full_name, is_active, created_at
        """
        users = User.objects.all().order_by("id")
        data = []
        for u in users:
            # derive full name
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
        """
        Create an auth user (writes to auth_user).
        Expected payload: { email, full_name (optional), password, is_active (optional) }
        """
        email = request.data.get("email")
        password = request.data.get("password")
        full_name = request.data.get("full_name", "") or ""
        is_active = request.data.get("is_active", True)

        if not email or not password:
            return Response({"detail": "email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        # username must be unique -- use email as username (common approach)
        username = email

        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=username).exists():
            return Response({"detail": "Email already exists."}, status=status.HTTP_400_BAD_REQUEST)

        parts = full_name.strip().split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # create_user will hash the password and set required fields
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

        # find user (if none, do not reveal)
        user = User.objects.filter(email__iexact=email).first()

        # generate OTP and hashed OTP for DB
        otp = _generate_numeric_otp(self.OTP_LENGTH)
        otp_hash = _hash_otp(otp, salt=email)
        now = timezone.now()

        # create PasswordResetOTP entry (store hashed OTP)
        otp_kwargs = {
            "email": email,
            "otp_hash": otp_hash,
            "created_at": now,
            "is_used": False,
        }
        # attach user if model supports it
        try:
            if user:
                otp_kwargs["user"] = user
        except Exception:
            # model might not accept user - ignore in that case
            pass

        PasswordResetOTP.objects.create(**otp_kwargs)

        # send OTP email (if email sending fails return 500; you can switch to console backend in dev)
        try:
            _send_otp_email(email, otp, minutes_valid=self.OTP_VALID_MINUTES)
        except Exception as exc:
            # Remove the OTP row if email failed (optional)
            PasswordResetOTP.objects.filter(email=email, otp_hash=otp_hash).delete()
            return Response({"detail": "Failed to send OTP email.", "error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Generic response so we don't leak user existence
        resp = {"detail": "If an account exists for this email, an OTP has been sent."}
        # Optionally include a uid/token if you want to continue supporting that flow
        if user:
            resp["uid"] = urlsafe_base64_encode(force_bytes(user.pk))
            # We still prefer the OTP path; token generation for immediate reset is possible but not required.
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
            return Response({"detail": "email and otp required."}, status=status.HTTP_400_BAD_REQUEST)

        # compute hash for submitted otp
        otp_hash = _hash_otp(otp, salt=email)

        # find most recent unused OTP record for this email
        otp_record = PasswordResetOTP.objects.filter(email__iexact=email, is_used=False).order_by("-created_at").first()
        if not otp_record:
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # check expiry
        if otp_record.created_at + timedelta(minutes=self.OTP_VALID_MINUTES) < timezone.now():
            return Response({"detail": "OTP expired."}, status=status.HTTP_400_BAD_REQUEST)

        # match hash
        if otp_record.otp_hash != otp_hash:
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # mark used
        otp_record.is_used = True
        otp_record.save(update_fields=["is_used"])

        # return uid:
        # Prefer returning base64(pk) when a user exists (keeps it consistent with ForgotPasswordView).
        # If no user exists (rare), return base64(email) to allow the frontend to continue flow without revealing existence.
        user = User.objects.filter(email__iexact=email).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
        else:
            uid = urlsafe_base64_encode(force_bytes(email))
        return Response({"detail": "OTP verified.", "uid": uid}, status=status.HTTP_200_OK)


# ----- Reset password ---------------------------------------------------------
# ----- Reset password ---------------------------------------------------------
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Expect payload: { uid, token (optional), new_password }
        uid may be base64-encoded email OR base64-encoded user.pk.

        NOTE: Some frontends send `token: null` which will fail serializers that
        disallow null. Normalize token to an empty string before validation.
        """
        # Copy incoming data to a plain dict and normalize token (avoid None)
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

        # normalize decoded value to avoid whitespace/case issues
        decoded_clean = decoded.strip()
        decoded_lower = decoded_clean.lower()

        user = None
        # Try interpret decoded as pk (integer)
        if decoded_clean.isdigit():
            try:
                user = User.objects.filter(pk=int(decoded_clean)).first()
            except Exception:
                user = None

        # If not found by pk, and looks like an email, search by email (case-insensitive)
        if not user and "@" in decoded_lower:
            user = User.objects.filter(email__iexact=decoded_lower).first()

        if not user:
            return Response({"detail": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Set new password
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

# ----- Logout -----------------------------------------------------------------
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "refresh token required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except Exception:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out."}, status=status.HTTP_200_OK)

