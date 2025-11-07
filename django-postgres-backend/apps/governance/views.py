from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from .models import AuditLog


class HealthView(APIView):
    def get(self, request):
        return Response({"ok": True})


class AuditLogListView(generics.ListAPIView):
    serializer_class = None  # We can emit minimal dicts

    def get_queryset(self):
        return AuditLog.objects.all()

    def list(self, request, *args, **kwargs):
        qs = AuditLog.objects.all()
        table_name = request.query_params.get("table_name")
        action = request.query_params.get("action")
        if table_name:
            qs = qs.filter(table_name=table_name)
        if action:
            qs = qs.filter(action=action)
        data = list(
            qs.order_by("-created_at").values(
                "id", "actor_user_id", "action", "table_name", "record_id", "created_at"
            )
        )
        return Response(data)

