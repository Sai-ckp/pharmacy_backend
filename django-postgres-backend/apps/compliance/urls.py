from django.urls import path, include
<<<<<<< HEAD
from .views import HealthView
from rest_framework.routers import DefaultRouter
from .views import PrescriptionViewSet, H1RegisterEntryViewSet, NDPSDailyEntryViewSet, RecallEventViewSet

router = DefaultRouter()
router.register(r'prescriptions', PrescriptionViewSet)
router.register(r'h1-register', H1RegisterEntryViewSet)
router.register(r'ndps-daily', NDPSDailyEntryViewSet)
router.register(r'recall-events', RecallEventViewSet)

urlpatterns = [
    path('health/', HealthView.as_view(), name='compliance-health'),
    path('', include(router.urls)),
]
=======
from rest_framework.routers import DefaultRouter
from .views import PrescriptionViewSet, H1RegisterEntryViewSet, NDPSDailyEntryViewSet, RecallEventViewSet

router = DefaultRouter()
router.register(r"prescriptions", PrescriptionViewSet, basename="prescription")
router.register(r"h1-register", H1RegisterEntryViewSet, basename="h1")
router.register(r"ndps-daily", NDPSDailyEntryViewSet, basename="ndps")
router.register(r"recall-events", RecallEventViewSet, basename="recall")

urlpatterns = [path("", include(router.urls))]
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
