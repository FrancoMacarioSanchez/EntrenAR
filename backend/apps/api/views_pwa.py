"""Sirve la PWA compilada (frontend -> npm run build -> backend/pwa_dist)."""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")


def pwa_app(request, path=""):
    root = Path(settings.PWA_DIST).resolve()
    if path:
        f = (root / path).resolve()
        if root in f.parents and f.is_file():
            resp = FileResponse(open(f, "rb"), content_type=mimetypes.guess_type(str(f))[0])
            if f.name in ("sw.js", "index.html", "manifest.webmanifest", "registerSW.js"):
                resp["Cache-Control"] = "no-cache"
                if f.name == "sw.js":
                    resp["Service-Worker-Allowed"] = "/app/"
            else:
                resp["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        if "." in Path(path).name:
            raise Http404
    index = root / "index.html"
    if not index.exists():
        return HttpResponse(
            "<h2>La PWA todavía no está compilada.</h2><p>En la carpeta <code>frontend</code> ejecutá "
            "<code>npm install</code> y <code>npm run build</code>, o usá <code>npm run dev</code> "
            "(http://demo.localhost:5173/app/).</p>", status=503)
    resp = FileResponse(open(index, "rb"), content_type="text/html")
    resp["Cache-Control"] = "no-cache"
    return resp


def pwa_manifest(request):
    """Manifest por gimnasio: la app instalada lleva el nombre y color de cada gimnasio."""
    from django.http import JsonResponse

    from apps.core.models import GymSettings

    cfg = GymSettings.get()
    data = {
        "name": cfg.display_name, "short_name": cfg.display_name[:12], "description": f"App de {cfg.display_name}",
        "id": "/app/", "start_url": "/app/", "scope": "/app/", "display": "standalone", "orientation": "portrait",
        "background_color": "#0b0d11", "theme_color": cfg.primary_color, "lang": "es-AR",
        "icons": [
            {"src": "/app/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/app/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/app/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Entrenar", "url": "/app/entrenar"},
            {"name": "Mi QR de ingreso", "url": "/app/membresia"},
            {"name": "Cargar medidas", "url": "/app/cuerpo"},
        ],
    }
    resp = JsonResponse(data, content_type="application/manifest+json", json_dumps_params={"ensure_ascii": False})
    resp["Cache-Control"] = "no-cache"
    return resp
