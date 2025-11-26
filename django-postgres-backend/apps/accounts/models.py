from django.db import models
from django.utils import timezone


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.code


class User(models.Model):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.email


class UserRole(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    role = models.ForeignKey('accounts.Role', on_delete=models.CASCADE)

    class Meta:
        unique_together = (('user', 'role'),)


class UserDevice(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    device_id = models.CharField(max_length=200, unique=True)
    user_agent = models.CharField(max_length=255, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)


class PasswordResetOTP(models.Model):
    email = models.EmailField()
    otp_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["email", "created_at"]),
        ]

    def is_expired(self, ttl_minutes=10):
        return self.created_at < timezone.now() - timezone.timedelta(minutes=ttl_minutes)

