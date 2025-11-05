from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=32, unique=True, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True)
    consent_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"
