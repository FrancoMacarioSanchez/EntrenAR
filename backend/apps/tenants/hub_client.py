"""EntrenAR -> CoreX Hub (contrato docs/API_SAAS.md del Hub).

Dos envíos, ambos con `Authorization: Bearer <HUB_INGEST_TOKEN>` (el "token de ingesta" del servicio en el Hub):

* POST {HUB_URL}/api/v1/metricas/        {"items": [{"tenant", "fecha", "metricas"}]}  (máx. 500 por llamada)
* POST {HUB_URL}/api/v1/tenants/estado/  {"tenant", "estado", "dominio", "id", "error"}

Todo pasa por la cola HubEvent: si el Hub no responde se reintenta con espera exponencial.
Las métricas de un mismo día se pueden reenviar: el Hub las fusiona (idempotente).
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import HubEvent

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 12
BATCH = 200
METRICS_PATH = "/api/v1/metricas/"
STATE_PATH = "/api/v1/tenants/estado/"


class PermanentError(Exception):
    """El Hub rechazó el envío por los datos (4xx): no tiene sentido reintentar."""


def hub_enabled():
    return bool(settings.HUB_URL and settings.HUB_INGEST_TOKEN)


def _post(path, body):
    import requests

    r = requests.post(settings.HUB_URL.rstrip("/") + path, data=json.dumps(body, default=str), timeout=15,
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.HUB_INGEST_TOKEN}"})
    if r.status_code in (400, 404, 413, 422):
        raise PermanentError(f"HTTP {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json() if r.content else {}


# ------------------------------------------------------------------ encolar

def push_state(gym, error=""):
    """Encola el estado actual del gimnasio para el Hub."""
    if not hub_enabled() or gym.is_public:
        return None
    from .corex_api import serialize

    data = serialize(gym)
    body = {"tenant": gym.schema_name, "estado": "error" if error else data["estado"],
            "dominio": data["dominio"], "id": str(gym.pk)}
    if error:
        body["error"] = error[:1000]
    return HubEvent.objects.create(event="estado", tenant_slug=gym.slug, payload=body)


def push_metrics(gym, days, price=None):
    """Encola las métricas de `days` (fechas) de un gimnasio. Corre en el schema público."""
    if not hub_enabled() or gym.is_public:
        return None
    from django_tenants.utils import tenant_context

    from .corex_metrics import collect

    items = []
    with tenant_context(gym):
        for d in days:
            items.append({"tenant": gym.schema_name, "fecha": d.isoformat(), "metricas": collect(gym, d, price=price)})
    if not items:
        return None
    return HubEvent.objects.create(event="metricas", tenant_slug=gym.slug, payload={"items": items})


# ------------------------------------------------------------------ enviar

def _send(ev):
    if ev.event == "estado":
        return _post(STATE_PATH, ev.payload)
    if ev.event == "metricas":
        resp = _post(METRICS_PATH, {"items": ev.payload.get("items", [])[:500]})
        if resp.get("rechazados"):
            # Tenant que el Hub no conoce (p. ej. alta directa en EntrenAR que nadie importó): queda registrado.
            ev.last_error = "Rechazados por el Hub: " + json.dumps(resp["rechazados"], ensure_ascii=False)[:900]
        return resp
    raise PermanentError(f"Evento desconocido: {ev.event}")


def process_pending(limit=500):
    """Manda lo pendiente. Devuelve (enviados, fallidos)."""
    if not hub_enabled():
        return 0, 0
    ok = fail = 0
    qs = HubEvent.objects.filter(sent_at__isnull=True, attempts__lt=MAX_ATTEMPTS, next_try_at__lte=timezone.now())
    for ev in qs[:limit]:
        ev.last_error = ""
        try:
            _send(ev)
            ev.sent_at = timezone.now()
            ok += 1
        except PermanentError as exc:
            ev.attempts = MAX_ATTEMPTS  # no se reintenta; queda visible en el admin
            ev.last_error = str(exc)[:1000]
            fail += 1
            log.warning("Hub rechazó %s %s: %s", ev.event, ev.event_id, exc)
        except Exception as exc:  # noqa: BLE001 - red / 5xx: se reintenta
            ev.attempts += 1
            ev.last_error = str(exc)[:1000]
            ev.next_try_at = timezone.now() + timedelta(minutes=2 ** min(ev.attempts, 10))
            fail += 1
            log.warning("Hub %s %s falló (intento %s): %s", ev.event, ev.event_id, ev.attempts, exc)
        ev.save()
    return ok, fail


def queue_health():
    pending = HubEvent.objects.filter(sent_at__isnull=True)
    return {
        "pendientes": pending.filter(attempts__lt=MAX_ATTEMPTS).count(),
        "fallidos": pending.filter(attempts__gte=MAX_ATTEMPTS).count(),
        "ultimo_envio": HubEvent.objects.filter(sent_at__isnull=False).order_by("-sent_at")
                                       .values_list("sent_at", flat=True).first(),
    }


def ping():
    """Prueba la conexión (GET /api/v1/ping/). Devuelve (ok, detalle)."""
    import requests

    if not hub_enabled():
        return False, "HUB_URL / HUB_INGEST_TOKEN sin configurar"
    try:
        r = requests.get(settings.HUB_URL.rstrip("/") + "/api/v1/ping/", timeout=10,
                         headers={"Authorization": f"Bearer {settings.HUB_INGEST_TOKEN}"})
        return r.ok, r.text[:300]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
