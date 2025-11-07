from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from .models import TransferVoucher
from .serializers import TransferVoucherSerializer
from . import services

class TransferVoucherViewSet(viewsets.ModelViewSet):
    queryset = TransferVoucher.objects.all().select_related("from_location", "to_location")
    serializer_class = TransferVoucherSerializer
    permission_classes = [AllowAny]
    permission_classes = [IsAuthenticated]


    @action(detail=True, methods=["post"], url_path="post")
    def post_transfer(self, request, pk=None):
        voucher = self.get_object()
        try:
            res = services.post_transfer(voucher.id, actor=request.user)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(res, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        try:
            res = services.receive_transfer(pk, actor=request.user)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(res, status=status.HTTP_200_OK)
