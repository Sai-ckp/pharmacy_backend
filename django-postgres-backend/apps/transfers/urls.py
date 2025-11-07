from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TransferVoucherViewSet

router = DefaultRouter()
router.register(r"vouchers", TransferVoucherViewSet, basename="transfer-voucher")

urlpatterns = [path("", include(router.urls))]
