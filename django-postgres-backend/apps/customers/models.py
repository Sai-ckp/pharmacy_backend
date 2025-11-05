from django.db import models
from django.utils import timezone


class Customer(models.Model):
    class Type(models.TextChoices):
        RETAIL = "RETAIL", "Retail"
        WHOLESALE = "WHOLESALE", "Wholesale"
        HOSPITAL = "HOSPITAL", "Hospital"

    name = models.CharField(max_length=255,blank=True, null=True) #made blank and null to avoid migrationsissues
    phone = models.CharField(max_length=20, unique=True,blank=True, null=True) #made blank and null to avoid migrationsissues
    email = models.EmailField(blank=True, null=True)
    gstin = models.CharField(max_length=32, blank=True, null=True)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.RETAIL)
    price_tier = models.CharField(max_length=64, blank=True, null=True)

    billing_address = models.TextField(blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=64, blank=True, null=True)
    state_code = models.CharField(max_length=8, blank=True, null=True)
    pincode = models.CharField(max_length=12, blank=True, null=True)

    consent_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["name"]), models.Index(fields=["phone"])]

    def __str__(self):
        return f"{self.name} ({self.phone})"
