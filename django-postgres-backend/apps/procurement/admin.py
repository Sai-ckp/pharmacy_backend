from django.contrib import admin
from .models import Vendor, Purchase, PurchaseLine, PurchasePayment, PurchaseDocument, VendorReturn

admin.site.register(Vendor)
admin.site.register(Purchase)
admin.site.register(PurchaseLine)
admin.site.register(PurchasePayment)
admin.site.register(PurchaseDocument)
admin.site.register(VendorReturn)

