from django.db import models


class Settings(models.Model):
    key = models.CharField(primary_key=True, max_length=120)
    value = models.CharField(max_length=500)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.key}={self.value}"


class BusinessProfile(models.Model):
    name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    gstin = models.CharField(max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

