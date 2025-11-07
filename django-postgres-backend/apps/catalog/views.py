from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from .models import ProductCategory, Product, BatchLot
from .serializers import ProductCategorySerializer, ProductSerializer, BatchLotSerializer


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class BatchLotViewSet(viewsets.ModelViewSet):
    queryset = BatchLot.objects.all()
    serializer_class = BatchLotSerializer

