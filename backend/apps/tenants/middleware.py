"""Bloquea el gimnasio cuando la suscripción SaaS está suspendida / vencida."""
from django.http import JsonResponse
from django.shortcuts import redirect

ALLOWED_PREFIXES = (
    "/static/", "/media/", "/login", "/logout", "/sso/", "/cuenta/suscripcion", "/cuenta/password",
    "/cuenta/exportar", "/cuenta/activar", "/webhooks/", "/app", "/api/v1/auth/", "/api/v1/me/",
)


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        request.gym = tenant
        if tenant is not None and not tenant.is_public and tenant.is_blocked:
            path = request.path
            if not path.startswith(ALLOWED_PREFIXES):
                if path.startswith("/api/"):
                    return JsonResponse({"detail": "El gimnasio tiene la suscripción suspendida.",
                                         "code": "gym_blocked"}, status=402)
                return redirect("panel:subscription")
        return self.get_response(request)
