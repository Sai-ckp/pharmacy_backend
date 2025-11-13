from __future__ import annotations

from decimal import Decimal


def compute_po_line_totals(*, qty_packs: Decimal, unit_cost_pack: Decimal, product_gst_percent: Decimal, gst_override: Decimal | None) -> dict:
    qty = Decimal(qty_packs or 0)
    cost = Decimal(unit_cost_pack or 0)
    pct = Decimal(gst_override) if gst_override is not None else Decimal(product_gst_percent or 0)
    gross = qty * cost
    tax = (gross * pct / Decimal("100")).quantize(Decimal("0.01"))
    return {"gross": gross.quantize(Decimal("0.01")), "tax": tax, "pct": pct}

