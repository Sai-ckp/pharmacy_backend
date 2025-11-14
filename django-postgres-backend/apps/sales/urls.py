from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SalesInvoiceViewSet, SalesPaymentViewSet,
    BillingStatsView, MedicinesSuggestView, InvoiceQuoteView,
)

router = DefaultRouter()
router.register(r"invoices", SalesInvoiceViewSet, basename="sales-invoice")
router.register(r"payments", SalesPaymentViewSet, basename="sales-payment")

urlpatterns = [
    path("", include(router.urls)),
    path("billing/stats/", BillingStatsView.as_view(), name="billing-stats"),
    path("billing/medicines/", MedicinesSuggestView.as_view(), name="billing-medicines"),
    path("invoices/quote/", InvoiceQuoteView.as_view(), name="sales-invoice-quote"),
]
