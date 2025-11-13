from rest_framework.permissions import IsAuthenticatedOrReadOnly as DRFIsAuthenticatedOrReadOnly


class IsAuthenticatedOrReadOnly(DRFIsAuthenticatedOrReadOnly):
    pass

