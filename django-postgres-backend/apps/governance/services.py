from __future__ import annotations

from django.db import transaction
from typing import Optional

from .models import AuditLog, SystemEvent
from .middleware import get_request_id


@transaction.atomic
def audit(
    actor,
    table: str,
    row_id: int,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
) -> None:
    AuditLog.objects.create(
        actor_user=actor if getattr(actor, "id", None) else None,
        action=action,
        table_name=table,
        record_id=str(row_id),
        before_json=before,
        after_json=after,
        ip=(meta or {}).get("ip", ""),
        user_agent=((meta or {}).get("user_agent", "") + (f" req_id={get_request_id('')}" if get_request_id('') else "")).strip(),
    )


def emit_event(code: str, payload: dict) -> None:
    SystemEvent.objects.create(code=code, payload=payload or {})


def run_expiry_scan() -> dict:
    from datetime import date, timedelta
    from apps.catalog.models import BatchLot
    from apps.settingsx.services import get_setting

    try:
        warn_days = int(get_setting("ALERT_EXPIRY_WARNING_DAYS", "60") or 60)
        crit_days = int(get_setting("ALERT_EXPIRY_CRITICAL_DAYS", "30") or 30)
    except Exception:
        warn_days, crit_days = 60, 30
    today = date.today()
    warn_cutoff = today + timedelta(days=warn_days)
    crit_cutoff = today + timedelta(days=crit_days)

    updated = {"EXPIRED": 0}
    # Mark EXPIRED
    expired = BatchLot.objects.filter(expiry_date__lt=today).exclude(status=BatchLot.Status.EXPIRED)
    updated["EXPIRED"] = expired.update(status=BatchLot.Status.EXPIRED)

    emit_event(
        "EXPIRY_SCAN",
        {"warning_days": warn_days, "critical_days": crit_days, "ts": str(today)},
    )
    return {"updated": updated}


def run_low_stock_scan() -> list[dict]:
    from decimal import Decimal
    from apps.inventory.services import low_stock
    # For simplicity, run across all locations by id
    from apps.locations.models import Location

    results = []
    for loc in Location.objects.filter(is_active=True).values_list("id", flat=True):
        results.extend(low_stock(loc))
    emit_event("LOW_STOCK_SCAN", {"count": len(results)})
    return results
