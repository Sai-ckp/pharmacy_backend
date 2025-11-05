from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SalesInvoiceViewSet, SalesPaymentViewSet

router = DefaultRouter()
router.register(r"invoices", SalesInvoiceViewSet, basename="sales-invoice")
router.register(r"payments", SalesPaymentViewSet, basename="sales-payment")

urlpatterns = [path("", include(router.urls))]
