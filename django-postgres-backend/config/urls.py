from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path("api/v1/customers/", include("apps.customers.urls")),
    path("api/v1/sales/", include("apps.sales.urls")),
    path("api/v1/transfers/", include("apps.transfers.urls")),
    path("api/v1/compliance/", include("apps.compliance.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    # Dev A app mounts
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/locations/', include('apps.locations.urls')),
    path('api/v1/catalog/', include('apps.catalog.urls')),
    path('api/v1/inventory/', include('apps.inventory.urls')),
    path('api/v1/procurement/', include('apps.procurement.urls')),
    path('api/v1/settings/', include('apps.settingsx.urls')),
    path('api/v1/governance/', include('apps.governance.urls')),
]
