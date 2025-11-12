from django.urls import path
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('api/_health', views.health, name='health'),
]
