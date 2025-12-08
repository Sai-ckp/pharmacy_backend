from django.db import models
from django.utils import timezone


class ExampleModel(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SystemLicense(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        SUSPENDED = "SUSPENDED", "Suspended"

    license_key = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    valid_from = models.DateField()
    valid_to = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-valid_to",)

    def __str__(self) -> str:
        return f"{self.license_key} ({self.status})"

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.valid_from <= today <= self.valid_to

    @property
    def days_left(self) -> int:
        today = timezone.localdate()
        return max(0, (self.valid_to - today).days)


def get_current_license():
    return SystemLicense.objects.filter(status=SystemLicense.Status.ACTIVE).order_by("-valid_to").first()

