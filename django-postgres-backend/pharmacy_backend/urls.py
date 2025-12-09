from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts.views import LoginView
from core.views import HealthCheckView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    # Health check endpoint for Azure/App Service
    path("api/health/", HealthCheckView.as_view(), name="api_health"),
    # Auth (JWT)
    path("api/auth/login/", LoginView.as_view(), name="api_auth_login"),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Dev B apps
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
    path('api/v1/dashboard/', include('apps.dashboard.urls')),
    path('api/v1/masters/', include('apps.settingsx.masters_urls')),
    path('api/v1/governance/', include('apps.governance.urls')),
    # OpenAPI schema + Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
