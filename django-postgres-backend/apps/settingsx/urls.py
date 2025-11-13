from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    HealthView, SettingsListCreateView, SettingsDetailView, BusinessProfileView,
    SettingsGroupView, DocCounterViewSet, KVDetailView, DocCounterNextView,
    PaymentMethodViewSet, PaymentTermViewSet, BackupRestoreView,
)


router = DefaultRouter()
router.register(r'counters', DocCounterViewSet)
router.register(r'payment-methods', PaymentMethodViewSet)
router.register(r'payment-terms', PaymentTermViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='settings-root'),
    # Legacy list endpoints
    path('settings/', SettingsListCreateView.as_view(), name='settings-list'),
    path('settings/<str:pk>/', SettingsDetailView.as_view(), name='settings-detail'),
    # Spec endpoints
    path('kv/<str:key>/', KVDetailView.as_view(), name='settings-kv-detail'),
    path('business-profile/', BusinessProfileView.as_view(), name='business-profile'),
    path('doc-counters/next/', DocCounterNextView.as_view(), name='doc-counters-next'),
    path('backup/restore/', BackupRestoreView.as_view(), name='backup-restore'),
    path('app/', SettingsGroupView.as_view(), name='settings-group'),
    path('', include(router.urls)),
]

