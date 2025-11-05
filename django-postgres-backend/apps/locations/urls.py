from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HealthView, LocationViewSet

router = DefaultRouter()
router.register(r'locations', LocationViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='locations-root'),
    path('', include(router.urls)),
]

