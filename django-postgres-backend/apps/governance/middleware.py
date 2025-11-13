import threading
import uuid

_local = threading.local()


def get_request_id(default: str | None = None) -> str | None:
    return getattr(_local, "request_id", default)


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        _local.request_id = rid
        response = self.get_response(request)
        response["X-Request-Id"] = rid
        return response

