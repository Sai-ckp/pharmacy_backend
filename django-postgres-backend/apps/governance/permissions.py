from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        try:
            roles = getattr(user, "roles", None)
            if roles is None:
                return False
            return roles.filter(code="ADMIN").exists()
        except Exception:
            return False

