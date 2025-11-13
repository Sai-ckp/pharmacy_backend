from rest_framework import viewsets, filters, permissions
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("name")
    serializer_class = CustomerSerializer
    permission_classes = [permissions.AllowAny] #allowany only for the testing purpose,change it later
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "gstin", "code"]
    ordering_fields = ["name", "type", "credit_limit", "outstanding_balance"]
    
