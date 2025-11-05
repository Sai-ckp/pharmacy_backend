from django.db import models


class Settings(models.Model):
    key = models.CharField(primary_key=True, max_length=120)
    value = models.CharField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.key}={self.value}"


class BusinessProfile(models.Model):
    business_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.TextField(blank=True)
    owner_name = models.CharField(max_length=200, blank=True)
    registration_date = models.DateField(null=True, blank=True)
    gst_number = models.CharField(max_length=64, blank=True)
    pharmacy_license_number = models.CharField(max_length=64, blank=True)
    drug_license_number = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DocCounter(models.Model):
    document_type = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=16)
    next_number = models.IntegerField(default=1)
    padding_int = models.IntegerField(default=4)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.document_type}:{self.prefix}{self.next_number}"


class BackupArchive(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'SUCCESS'
        FAILED = 'FAILED', 'FAILED'

    file_url = models.URLField()
    size_bytes = models.BigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUCCESS)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)

