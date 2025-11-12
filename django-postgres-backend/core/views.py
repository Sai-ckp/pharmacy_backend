from django.http import JsonResponse


def home(request):
    return JsonResponse({"message": "Welcome to the Django PostgreSQL backend!"})


def health(request):
    return JsonResponse({"ok": True})

