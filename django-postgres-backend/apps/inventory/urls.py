from django.urls import path
from .views import (
    HealthView,
    BatchesListView,
    StockOnHandView,
    MovementsCreateView,
    LowStockView,
    ExpiringView,
    RackLocationViewSet,
    InventoryStatsView,
    MovementsListView,
    StockSummaryView,
    AddMedicineView,
    MedicinesListView,
)
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r'rack-locations', RackLocationViewSet, basename='rack-location')

urlpatterns = [
    path('', HealthView.as_view(), name='inventory-root'),
    path('batches/', BatchesListView.as_view(), name='inventory-batches'),
    path('stock-on-hand/', StockOnHandView.as_view(), name='inventory-stock-on-hand'),
    path('stock-summary/', StockSummaryView.as_view(), name='inventory-stock-summary'),
    path('movements/', MovementsCreateView.as_view(), name='inventory-movements'),
    path('movements/list', MovementsListView.as_view(), name='inventory-movements-list'),
    path('low-stock/', LowStockView.as_view(), name='inventory-low-stock'),
    path('expiring/', ExpiringView.as_view(), name='inventory-expiring'),
    path('stats/', InventoryStatsView.as_view(), name='inventory-stats'),
    path('add-medicine/', AddMedicineView.as_view(), name='inventory-add-medicine'),
    path('medicines/', MedicinesListView.as_view(), name='inventory-medicines'),
]

urlpatterns += router.urls

