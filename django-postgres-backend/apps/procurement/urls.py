from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HealthView, VendorViewSet, PurchaseViewSet, PurchasePaymentViewSet,
    PurchaseDocumentViewSet, VendorReturnViewSet
)

router = DefaultRouter()
router.register(r'vendors', VendorViewSet)
router.register(r'purchases', PurchaseViewSet)
router.register(r'payments', PurchasePaymentViewSet)
router.register(r'documents', PurchaseDocumentViewSet)
router.register(r'vendor-returns', VendorReturnViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='procurement-root'),
    path('', include(router.urls)),
]

