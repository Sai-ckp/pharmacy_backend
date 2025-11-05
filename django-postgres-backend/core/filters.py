from django_filters.rest_framework import FilterSet
from rest_framework.filters import SearchFilter, OrderingFilter


class SearchOrderingMixin:
    filter_backends = [SearchFilter, OrderingFilter]

