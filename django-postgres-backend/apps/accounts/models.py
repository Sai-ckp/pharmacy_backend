
from django.conf import settings
from django.db import models
from django.utils import timezone


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)

    def __str__(self):
        return self.code


class User(models.Model):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class UserRole(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    role = models.ForeignKey("accounts.Role", on_delete=models.CASCADE)

    class Meta:
        unique_together = (("user", "role"),)


class UserDevice(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device",
    )
    device_id = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    last_login_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["device_id"], name="accounts_userdevice_device_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.device_id}"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="password_reset_otps",
    )
    email = models.EmailField()
    otp_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["email", "created_at"], name="accounts_pa_email_9a1f52_idx")
        ]

