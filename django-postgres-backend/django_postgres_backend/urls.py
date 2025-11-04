from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path("api/customers/", include("apps.customers.urls")),
    path("api/v1/sales/", include("apps.sales.urls")),
    path("api/v1/transfers/", include("apps.transfers.urls")),
    path("api/v1/compliance/", include("apps.compliance.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
]
