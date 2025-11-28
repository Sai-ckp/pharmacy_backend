from apps.settingsx.models import SettingKV, AlertThresholds


def _get_int_setting(key: str, default: int) -> int:
    try:
        return int(SettingKV.objects.get(key=key).value)
    except SettingKV.DoesNotExist:
        return int(default)
    except Exception:
        return int(default)


def get_stock_thresholds():
    thresholds = AlertThresholds.objects.first()
    if thresholds:
        return thresholds.low_stock_default, thresholds.low_stock_default // 5 if thresholds.low_stock_default else 10
    low = _get_int_setting("low_stock_threshold", 50)
    critical = _get_int_setting("critical_stock_threshold", 10)
    return low, critical
