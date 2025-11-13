from django.urls import path
from .views import HealthView, AuditLogListView, RunExpiryScanView, RunLowStockScanView


urlpatterns = [
    path('', HealthView.as_view(), name='governance-root'),
    path('audit-logs/', AuditLogListView.as_view(), name='audit-logs'),
    path('run/expiry-scan', RunExpiryScanView.as_view(), name='run-expiry-scan'),
    path('run/low-stock-scan', RunLowStockScanView.as_view(), name='run-low-stock-scan'),
]

