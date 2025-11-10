from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PrescriptionViewSet,
    H1RegisterEntryViewSet,
    NDPSDailyEntryViewSet,
    RecallEventViewSet,
)

router = DefaultRouter()
router.register(r"prescriptions", PrescriptionViewSet)
router.register(r"h1-register", H1RegisterEntryViewSet)
router.register(r"ndps-daily", NDPSDailyEntryViewSet)
router.register(r"recall-events", RecallEventViewSet)

urlpatterns = [path("", include(router.urls))]
