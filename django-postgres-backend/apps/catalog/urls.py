from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HealthView, ProductCategoryViewSet, ProductViewSet, BatchLotViewSet

router = DefaultRouter()
router.register(r'categories', ProductCategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'batches', BatchLotViewSet)

urlpatterns = [
    path('', HealthView.as_view(), name='catalog-root'),
    path('', include(router.urls)),
]

