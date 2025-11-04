from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    # API v1 mounts
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/locations/', include('apps.locations.urls')),
    path('api/v1/catalog/', include('apps.catalog.urls')),
    path('api/v1/inventory/', include('apps.inventory.urls')),
    path('api/v1/procurement/', include('apps.procurement.urls')),
    path('api/v1/settings/', include('apps.settingsx.urls')),
    path('api/v1/governance/', include('apps.governance.urls')),
]
