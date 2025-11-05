from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PrescriptionViewSet, H1RegisterEntryViewSet, NDPSDailyEntryViewSet, RecallEventViewSet

router = DefaultRouter()
router.register(r"prescriptions", PrescriptionViewSet, basename="prescription")
router.register(r"h1-register", H1RegisterEntryViewSet, basename="h1")
router.register(r"ndps-daily", NDPSDailyEntryViewSet, basename="ndps")
router.register(r"recall-events", RecallEventViewSet, basename="recall")

urlpatterns = [path("", include(router.urls))]
