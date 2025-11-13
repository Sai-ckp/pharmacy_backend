from django.db import models


class Location(models.Model):
    class Type(models.TextChoices):
        SHOP = "SHOP", "SHOP"
        WAREHOUSE = "WAREHOUSE", "WAREHOUSE"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.SHOP)
    address = models.TextField(blank=True)
    state_code = models.CharField(max_length=8, blank=True)
    gstin = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

