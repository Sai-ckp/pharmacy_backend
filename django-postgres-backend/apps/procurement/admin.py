from django.contrib import admin
from .models import (
    Vendor, Purchase, PurchaseLine, PurchasePayment, PurchaseDocument, VendorReturn,
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
)

admin.site.register(Vendor)
admin.site.register(Purchase)
admin.site.register(PurchaseLine)
admin.site.register(PurchasePayment)
admin.site.register(PurchaseDocument)
admin.site.register(VendorReturn)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderLine)
admin.site.register(GoodsReceipt)
admin.site.register(GoodsReceiptLine)

