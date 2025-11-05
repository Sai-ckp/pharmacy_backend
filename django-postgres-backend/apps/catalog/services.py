"""
Batch sellability rules

Policy:
- Batch must be in ACTIVE status, and
- Must not be expired as of "as_of" (defaults to today).

This module intentionally keeps the logic small and query-free for easy reuse.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Optional, Union

from .models import BatchLot


def is_batch_sellable(batch: Union[BatchLot, int], as_of: Optional[_date] = None) -> bool:
    """Return True if the batch can be sold under the active policy.

    Args:
        batch: BatchLot instance or its primary key.
        as_of: Date to compare expiry against; defaults to today.
    """
    obj: BatchLot
    if isinstance(batch, BatchLot):
        obj = batch
    else:
        obj = BatchLot.objects.get(pk=batch)

    if obj.status != BatchLot.Status.ACTIVE:
        return False

    as_of = as_of or _date.today()
    if obj.expiry_date and obj.expiry_date <= as_of:
        return False
    return True

