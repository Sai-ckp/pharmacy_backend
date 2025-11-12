from django.urls import path
from .views import (
    HealthView,
    BatchesListView,
    StockOnHandView,
    MovementsCreateView,
    LowStockView,
    ExpiringView,
    RackLocationViewSet,
)
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r'rack-locations', RackLocationViewSet, basename='rack-location')

urlpatterns = [
    path('', HealthView.as_view(), name='inventory-root'),
    path('batches/', BatchesListView.as_view(), name='inventory-batches'),
    path('stock-on-hand/', StockOnHandView.as_view(), name='inventory-stock-on-hand'),
    path('movements/', MovementsCreateView.as_view(), name='inventory-movements'),
    path('low-stock/', LowStockView.as_view(), name='inventory-low-stock'),
    path('expiring/', ExpiringView.as_view(), name='inventory-expiring'),
]

urlpatterns += router.urls

