from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions


def home(request):
    return JsonResponse({"message": "Welcome to the Django PostgreSQL backend!"})


def health(request):
    return JsonResponse({"ok": True})


class HealthCheckView(APIView):
    """Health check endpoint for Azure/App Service"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok"})

