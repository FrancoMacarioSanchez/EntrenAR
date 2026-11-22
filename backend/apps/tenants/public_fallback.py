"""Si alguien abre la app o la API sin el subdominio del gimnasio (ej. localhost en vez de demo.localhost)."""
from django.http import HttpResponse, JsonResponse

MSG = ("Esta dirección no corresponde a ningún gimnasio. Entrá con el subdominio del gimnasio, "
       "por ejemplo http://demo.localhost:8082/app/ (o http://demo.localhost:5173/app/ con npm run dev).")


def api_no_tenant(request, path=""):
    return JsonResponse({"detail": MSG, "code": "no_tenant"}, status=404)


def app_no_tenant(request, path=""):
    return HttpResponse(f"<div style='font-family:system-ui;max-width:560px;margin:60px auto'><h2>Falta el gimnasio</h2>"
                        f"<p>{MSG}</p></div>", status=404)
