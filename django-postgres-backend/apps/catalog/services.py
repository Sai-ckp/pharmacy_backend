"""
Catalog batch sellability rules (docstring contract only for Day 1):

Rules:
- Batch must be in ACTIVE status.
- Must not be expired or blocked.
- Near-expiry policy is controlled by settings (e.g., expiry_threshold_days = 180).

Expected interface to be implemented Day 2:

def is_batch_sellable(batch_id, *, now=None) -> bool:
    """Return True if the batch can be sold under the active policy.
    Checks: ACTIVE status, not expired/blocked, and near-expiry threshold.
    """

def get_near_expiry_batches(location_id=None) -> list:
    """Return batches that are near expiry according to the threshold."""

"""

from datetime import date
from .models import BatchLot


def is_batch_sellable(batch_lot: BatchLot) -> bool:
    if batch_lot.status != BatchLot.Status.ACTIVE:
        return False
    if batch_lot.expiry_date and batch_lot.expiry_date <= date.today():
        return False
    return True

