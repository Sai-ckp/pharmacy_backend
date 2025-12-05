from django.urls import path
from .views import (
    HealthView,
    BatchesListView,
    StockOnHandView,
    MovementsCreateView,
    LowStockView,
    ExpiringView,
    ExpiryAlertsView,
    RackLocationViewSet,
    InventoryStatsView,
    MovementsListView,
    StockSummaryView,
    AddMedicineView,
    MedicineDetailView,
    MedicinesListView,
    GlobalMedicinesView,
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
    path('expiry-alerts/', ExpiryAlertsView.as_view(), name='inventory-expiry-alerts'),
    path('stats/', InventoryStatsView.as_view(), name='inventory-stats'),
    path('add-medicine/', AddMedicineView.as_view(), name='inventory-add-medicine'),
    path('medicines/', MedicinesListView.as_view(), name='inventory-medicines'),
    path('medicines/<int:batch_id>/', MedicineDetailView.as_view(), name='inventory-medicine-detail'),
    path('medicines/global/', GlobalMedicinesView.as_view(), name='inventory-medicines-global'),
]

urlpatterns += router.urls

