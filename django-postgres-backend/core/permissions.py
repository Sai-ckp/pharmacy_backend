from rest_framework.permissions import BasePermission, IsAuthenticatedOrReadOnly as DRFIsAuthenticatedOrReadOnly

from .models import get_current_license


class IsAuthenticatedOrReadOnly(DRFIsAuthenticatedOrReadOnly):
    pass


class HasActiveSystemLicense(BasePermission):
    message = (
        "Your license has expired or is inactive. Please contact support@ckpsoftware.com to renew your license."
    )

    def has_permission(self, request, view):
        license_obj = get_current_license()
        return bool(license_obj and license_obj.is_active)

