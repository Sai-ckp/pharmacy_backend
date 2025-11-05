from django.urls import path
from .views import HealthView, SettingsListCreateView, SettingsDetailView, BusinessProfileView


urlpatterns = [
    path('', HealthView.as_view(), name='settings-root'),
    path('settings/', SettingsListCreateView.as_view(), name='settings-list'),
    path('settings/<str:pk>/', SettingsDetailView.as_view(), name='settings-detail'),
    path('business-profile/', BusinessProfileView.as_view(), name='business-profile'),
]

