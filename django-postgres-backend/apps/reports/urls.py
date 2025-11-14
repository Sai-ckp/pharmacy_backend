from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReportExportViewSet,
    SalesSummaryView, PurchasesSummaryView, ExpiryReportView, TopSellingView,
)

router = DefaultRouter()
router.register(r"exports", ReportExportViewSet, basename="report-export")

urlpatterns = [
    path("", include(router.urls)),
    path("sales/summary/", SalesSummaryView.as_view(), name="reports-sales-summary"),
    path("purchases/summary/", PurchasesSummaryView.as_view(), name="reports-purchases-summary"),
    path("expiry/", ExpiryReportView.as_view(), name="reports-expiry"),
    path("sales/top-selling/", TopSellingView.as_view(), name="reports-top-selling"),
]

