from django.urls import path
from .masters_views import MastersCountsView

urlpatterns = [
    path('counts/', MastersCountsView.as_view(), name='masters-counts'),
]

