from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HealthView, VendorViewSet, PurchaseViewSet, PurchasePaymentViewSet,
    PurchaseDocumentViewSet, VendorReturnViewSet,
    PurchaseOrderViewSet, GoodsReceiptViewSet,
    GrnImportPdfView, PoImportCommitView, GrnImportCommitView,
)

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)
router.register(r'purchases', PurchaseViewSet)
router.register(r'payments', PurchasePaymentViewSet)
router.register(r'documents', PurchaseDocumentViewSet)
router.register(r'vendor-returns', VendorReturnViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'grns', GoodsReceiptViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='procurement-root'),
    path('', include(router.urls)),
    path('grns/import-pdf', GrnImportPdfView.as_view(), name='grns-import-pdf'),
    path('purchase-orders/import-commit', PoImportCommitView.as_view(), name='po-import-commit'),
    path('grns/import-commit', GrnImportCommitView.as_view(), name='grn-import-commit'),
]

