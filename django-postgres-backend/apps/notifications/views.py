from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Notification
from .serializers import NotificationSerializer
from . import services


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by("-created_at")
    serializer_class = NotificationSerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["post"], url_path="send")
    def send_now(self, request, pk=None):
        """Manually trigger sending of a notification."""
        notif = self.get_object()
        if notif.status == Notification.Status.SENT:
            return Response({"detail": "Already sent."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            services.dispatch_notification(notif)
            notif.status = Notification.Status.SENT
            notif.sent_at = timezone.now()
            notif.save(update_fields=["status", "sent_at"])
            return Response({"status": notif.status, "sent_at": notif.sent_at}, status=status.HTTP_200_OK)
        except Exception as e:
            notif.status = Notification.Status.FAILED
            notif.error = str(e)
            notif.save(update_fields=["status", "error"])
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        """Retry a failed notification."""
        notif = self.get_object()
        if notif.status != Notification.Status.FAILED:
            return Response({"detail": "Only failed notifications can be retried."}, status=status.HTTP_400_BAD_REQUEST)

        notif.status = Notification.Status.QUEUED
        notif.error = None
        notif.save(update_fields=["status", "error"])
        services.dispatch_notification(notif)
        return Response({"status": notif.status}, status=status.HTTP_200_OK)
