from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet
<<<<<<< HEAD
from django.urls import path, include

=======

from django.urls import path, include

>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
router = DefaultRouter()
router.register("", CustomerViewSet, basename="customer")

urlpatterns = [path("", include(router.urls))]
<<<<<<< HEAD
=======


router = DefaultRouter()
router.register(r'', CustomerViewSet, basename='customer')

urlpatterns = router.urls
>>>>>>> 38b44f7337d8ae7c8e6818d8f49439bd6ffc151a
