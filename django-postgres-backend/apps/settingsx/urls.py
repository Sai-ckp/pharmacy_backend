from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HealthView, SettingsListCreateView, SettingsDetailView, BusinessProfileView, SettingsGroupView, DocCounterViewSet


router = DefaultRouter()
router.register(r'counters', DocCounterViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='settings-root'),
    path('settings/', SettingsListCreateView.as_view(), name='settings-list'),
    path('settings/<str:pk>/', SettingsDetailView.as_view(), name='settings-detail'),
    path('business-profile/', BusinessProfileView.as_view(), name='business-profile'),
    path('app/', SettingsGroupView.as_view(), name='settings-group'),
    path('', include(router.urls)),
]

