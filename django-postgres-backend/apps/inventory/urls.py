from django.urls import path
from .views import HealthView, StockView, LowStockView, ExpirySoonView


urlpatterns = [
    path('', HealthView.as_view(), name='inventory-root'),
    path('stock', StockView.as_view(), name='inventory-stock'),
    path('stock-summary/', StockView.as_view(), name='inventory-stock-summary'),
    path('low-stock', LowStockView.as_view(), name='inventory-low-stock'),
    path('expiry-soon', ExpirySoonView.as_view(), name='inventory-expiry-soon'),
]

