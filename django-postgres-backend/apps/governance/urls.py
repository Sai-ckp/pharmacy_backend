from django.urls import path
from .views import HealthView, AuditLogListView


urlpatterns = [
    path('', HealthView.as_view(), name='governance-root'),
    path('audit-logs', AuditLogListView.as_view(), name='audit-logs'),
]

