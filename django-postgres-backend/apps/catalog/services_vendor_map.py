from __future__ import annotations

from typing import Optional
from .models import Product
from .models import VendorProductCode


def product_by_vendor_code(vendor_id: int, vendor_code: str) -> Optional[Product]:
    code = (vendor_code or "").strip()
    if not code:
        return None
    # First try product.code
    p = Product.objects.filter(code__iexact=code).first()
    if p:
        return p
    # Then mapping
    vp = VendorProductCode.objects.filter(vendor_id=vendor_id, vendor_code__iexact=code).first()
    return vp.product if vp else None

