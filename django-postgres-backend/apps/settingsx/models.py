from django.db import models


class SettingKV(models.Model):
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


class PaymentMethod(models.Model):
    class MethodType(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD_CREDIT = "CARD_CREDIT", "Card - Credit"
        CARD_DEBIT = "CARD_DEBIT", "Card - Debit"
        NET_BANKING = "NET_BANKING", "Net Banking"
        CREDIT = "CREDIT", "On Credit"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=512, null=True, blank=True)
    method_type = models.CharField(max_length=32, choices=MethodType.choices, default=MethodType.OTHER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="idx_paymethod_name"),
            models.Index(fields=["is_active"], name="idx_paymethod_active"),
        ]

    def __str__(self) -> str:
        return self.name


class PaymentTerm(models.Model):
    name = models.CharField(max_length=120, unique=True)
    days = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=512, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["name"], name="idx_payterm_name"),
            models.Index(fields=["is_active"], name="idx_payterm_active"),
        ]

    def __str__(self) -> str:
        return self.name


class NotificationSettings(models.Model):
    enable_email = models.BooleanField(default=False)
    low_stock_alerts = models.BooleanField(default=False)
    expiry_alerts = models.BooleanField(default=False)
    daily_reports = models.BooleanField(default=False)
    notification_email = models.EmailField(blank=True, null=True)
    enable_sms = models.BooleanField(default=False)
    sms_phone = models.CharField(max_length=32, blank=True, null=True)
    smtp_host = models.CharField(max_length=200, blank=True, null=True)
    smtp_port = models.IntegerField(default=587)
    smtp_username = models.CharField(max_length=200, blank=True, null=True)
    smtp_password = models.CharField(max_length=200, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class TaxBillingSettings(models.Model):
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    calc_method = models.CharField(max_length=16, default="INCLUSIVE")
    invoice_prefix = models.CharField(max_length=16, default="INV-")
    invoice_start = models.IntegerField(default=1)
    invoice_template = models.CharField(max_length=64, default="STANDARD")
    invoice_footer = models.CharField(max_length=512, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class AlertThresholds(models.Model):
    critical_expiry_days = models.PositiveIntegerField(default=30)
    warning_expiry_days = models.PositiveIntegerField(default=60)
    low_stock_default = models.PositiveIntegerField(default=50)
    updated_at = models.DateTimeField(auto_now=True)

