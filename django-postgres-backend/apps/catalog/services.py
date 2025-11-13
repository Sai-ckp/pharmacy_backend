from __future__ import annotations

from decimal import Decimal
from typing import Union

from .models import BatchLot, Product


def packs_to_base(product_id: int, qty_packs: Decimal) -> Decimal:
    p = Product.objects.get(id=product_id)
    return (Decimal(qty_packs) or Decimal("0")) * (p.units_per_pack or Decimal("0"))


def product_snapshot(product_id: int, batch_lot_id: int) -> dict:
    p = Product.objects.get(id=product_id)
    lot = BatchLot.objects.get(id=batch_lot_id)
    return {
        "product_name": p.name,
        "generic_name": p.generic_name,
        "hsn": p.hsn,
        "schedule": p.schedule,
        "pack_size": p.pack_size,
        "manufacturer": p.manufacturer,
        "mrp": str(p.mrp),
        "batch_no": lot.batch_no,
        "expiry_date": lot.expiry_date,
        "rack_no": lot.rack_no,
    }

