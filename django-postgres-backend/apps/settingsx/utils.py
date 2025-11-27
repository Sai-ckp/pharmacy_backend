from apps.settingsx.models import SettingKV
from rest_framework.exceptions import ValidationError

def get_stock_thresholds():
    try:
        low = int(SettingKV.objects.get(key="low_stock_threshold").value)
    except SettingKV.DoesNotExist:
        raise ValidationError({"detail": "low_stock_threshold not configured"})

    try:
        critical = int(SettingKV.objects.get(key="critical_stock_threshold").value)
    except SettingKV.DoesNotExist:
        raise ValidationError({"detail": "critical_stock_threshold not configured"})

    return low, critical
