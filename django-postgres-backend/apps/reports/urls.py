from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ReportExportViewSet

router = DefaultRouter()
router.register(r"exports", ReportExportViewSet, basename="report-export")

urlpatterns = [path("", include(router.urls))]

