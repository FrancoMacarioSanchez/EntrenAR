"""API CoreX de EntrenAR: el Hub la consume para crear, suspender y medir gimnasios.

Contrato común de todos los SaaS de CoreX: docs/API_SAAS.md del Hub. Montada en el urlconf público
como /corex/v1/ y protegida con `Authorization: Bearer <COREX_AGENT_TOKEN>`.
"""
import hmac
import json
import logging
import re
from datetime import date, timedelta
from functools import wraps

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django_tenants.utils import get_public_schema_name, tenant_context

from . import corex_metrics
from .models import Gym, SaasPlan

log = logging.getLogger(__name__)
SCHEMA_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
MAX_DAYS = 92
VERSION = "2.0.0"

def hub_state(gym):
    """Estado de EntrenAR → estado del Hub. Una prueba vencida o un pago fuera de gracia bloquean = suspendido."""
    if gym.status == Gym.Status.CANCELED:
        return "baja"
    return "suspendido" if gym.is_blocked else "activo"
# Claves de límites del Hub → campos del plan de EntrenAR
LIMIT_KEYS = {"socios_activos": "max_members", "usuarios_staff": "max_staff"}


def _error(msg, status):
    return JsonResponse({"error": msg}, status=status)


def api(methods):
    def deco(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return _error("Método no permitido", 405)
            if getattr(connection, "schema_name", get_public_schema_name()) != get_public_schema_name():
                return _error("No encontrado", 404)
            expected = settings.COREX_AGENT_TOKEN
            auth = request.headers.get("Authorization", "")
            if not expected or not hmac.compare_digest(auth, f"Bearer {expected}"):
                return _error("Token inválido", 401)
            data = {}
            if request.method == "POST":
                try:
                    data = json.loads(request.body or b"{}")
                except ValueError:
                    return _error("JSON inválido", 400)
            return view(request, data, *args, **kwargs)
        return wrapper
    return deco


def _gyms():
    return Gym.objects.exclude(schema_name=get_public_schema_name()).select_related("plan")


def _domain(gym):
    d = gym.domains.order_by("-is_primary").first()
    if not d:
        return ""
    return f"{d.domain}{settings.PUBLIC_PORT_SUFFIX}" if settings.DEBUG else d.domain


def serialize(gym):
    return {"id": gym.pk, "schema_name": gym.schema_name, "nombre": gym.name, "dominio": _domain(gym),
            "estado": hub_state(gym), "estado_entrenar": gym.effective_state,
            "referencia_hub": gym.hub_ref or ""}


def detail(gym):
    from .ai_billing import current_usage
    from .models import AIAddon

    addon = AIAddon.for_gym(gym)
    usage = current_usage(gym)
    out = serialize(gym)
    out.update({
        "plan": {"codigo": gym.plan.code, "nombre": gym.plan.name} if gym.plan else {},
        "limites": gym.effective_limits(),
        "prueba_hasta": gym.trial_ends_at.isoformat() if gym.trial_ends_at else None,
        "periodo_hasta": gym.current_period_end.isoformat() if gym.current_period_end else None,
        "base_de_datos": {"schema": gym.schema_name, "tamano_mb": corex_metrics.schema_size_mb(gym.schema_name)},
        "ia": {"habilitada": addon.allowed, "activa": addon.active, "tope_diario": addon.max_daily_limit,
               "limite_diario": addon.effective_daily_limit, "precio_1k_tokens": str(addon.price_per_1k_tokens),
               "mes_tokens": usage.tokens if usage else 0, "mes_importe": str(addon.cost_for(usage.tokens) if usage else 0)},
    })
    return out


def _gym_or_404(schema):
    g = _gyms().filter(schema_name=schema).first()
    return g, (None if g else _error("Tenant inexistente", 404))


def _find_plan(plan):
    """Plan del Hub → plan de EntrenAR, por nombre o código (sin distinguir mayúsculas)."""
    if not plan:
        return None, []
    name = str(plan.get("nombre") or plan.get("codigo") or "").strip()
    p = SaasPlan.objects.filter(name__iexact=name).first() or SaasPlan.objects.filter(code__iexact=name).first()
    if not p:
        return None, [f"El plan «{name}» no existe en EntrenAR: se dejó el plan por defecto. Crealo en el admin de "
                      "EntrenAR con el mismo nombre."]
    return p, []


def _apply_plan(gym, plan, limites):
    warnings = []
    p, warnings = _find_plan(plan)
    if p:
        gym.plan = p
    clean = {}
    for k, v in (limites or {}).items():
        try:
            clean[k] = float(v)
        except (TypeError, ValueError):
            warnings.append(f"Límite «{k}» ignorado: no es un número.")
    unknown = sorted(set(clean) - set(LIMIT_KEYS))
    if unknown:
        warnings.append(f"EntrenAR no aplica estos límites (solo informativos): {', '.join(unknown)}.")
    gym.hub_limits = clean
    gym.save(update_fields=["plan", "hub_limits"])
    return warnings


# ---------------------------------------------------------------------------- vistas

@api(["GET"])
def health(request, data):
    return JsonResponse({"ok": True, "servicio": "entrenar", "version": VERSION, "tenants": _gyms().count()})


@api(["GET", "POST"])
def tenants(request, data):
    if request.method == "GET":
        return JsonResponse({"tenants": [serialize(g) for g in _gyms()]})

    from .services import create_gym, invite_owner, make_schema_name

    schema = str(data.get("schema_name") or "").strip().lower()
    if not SCHEMA_RE.match(schema) or schema == get_public_schema_name():
        return _error("schema_name inválido", 400)
    existing = _gyms().filter(schema_name=schema).first()
    if existing:  # idempotente: el Hub puede reintentar
        return JsonResponse(detail(existing), status=200)

    # Subdominio: el que propone el Hub si es de nuestro dominio base; si no, sale del schema.
    base = settings.BASE_DOMAIN
    host = str(data.get("dominio") or "").split(":")[0].lower()
    slug = host[: -len(base) - 1] if host.endswith("." + base) else schema.replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)[:40].strip("-") or schema.replace("_", "-")
    if Gym.objects.filter(slug=slug).exists():
        return _error(f"El subdominio «{slug}» ya está en uso", 409)
    if make_schema_name(slug) != schema and Gym.objects.filter(schema_name=schema).exists():
        return _error("El schema ya está en uso", 409)

    cliente = data.get("cliente") or {}
    admin = data.get("admin") or {}
    if not admin.get("username"):
        return _error("Falta admin.username", 400)
    plan, warnings = _find_plan(data.get("plan"))
    try:
        gym, _ = create_gym(
            name=str(data.get("nombre") or cliente.get("empresa") or schema)[:120], slug=slug, schema_name=schema,
            cuit=str(cliente.get("cuit") or "")[:13], phone=str(cliente.get("telefono") or "")[:40],
            plan_code=plan.code if plan else None, admin_username=admin["username"][:150],
            admin_email=admin.get("email") or cliente.get("email") or "", admin_name=admin.get("nombre") or "",
            hub_ref=str(data.get("referencia_hub") or "") or None, invite=True,
        )
    except ValueError as e:
        return _error(str(e), 409)
    except Exception as e:  # noqa: BLE001 - se informa al Hub
        log.exception("Alta desde el Hub falló")
        return _error(f"No se pudo crear el gimnasio: {e}", 500)

    warnings += _apply_plan(gym, None, data.get("limites"))
    resp = detail(gym)
    sent, link = invite_owner(gym, admin["username"])
    if not sent:
        resp["link_invitacion"] = link
        warnings.append("No se pudo enviar el email de invitación: reenviá el link al cliente.")
    if warnings:
        resp["advertencias"] = warnings
    from .hub_client import push_state
    push_state(gym)
    return JsonResponse(resp, status=201)


@api(["GET"])
def tenant_detail(request, data, schema):
    g, err = _gym_or_404(schema)
    return err or JsonResponse(detail(g))


@api(["GET"])
def metrics(request, data, schema):
    g, err = _gym_or_404(schema)
    if err:
        return err
    try:
        to = date.fromisoformat(request.GET.get("hasta") or date.today().isoformat())
        frm = date.fromisoformat(request.GET.get("desde") or (to - timedelta(days=6)).isoformat())
    except ValueError:
        return _error("Fechas inválidas (YYYY-MM-DD)", 400)
    if frm > to or (to - frm).days > MAX_DAYS:
        return _error(f"Rango inválido (máximo {MAX_DAYS} días)", 400)
    series = []
    with tenant_context(g):
        d = frm
        while d <= to:
            series.append({"fecha": d.isoformat(), "metricas": corex_metrics.collect(g, d)})
            d += timedelta(days=1)
    return JsonResponse({"tenant": schema, "estado": hub_state(g), "series": series})


def _set_status(gym, status, reason=""):
    gym.status = status
    gym.suspended_reason = reason[:200] if status == Gym.Status.SUSPENDED else ""
    gym.save(update_fields=["status", "suspended_reason"])


@api(["POST"])
def suspend(request, data, schema):
    g, err = _gym_or_404(schema)
    if err:
        return err
    _set_status(g, Gym.Status.SUSPENDED, str(data.get("motivo") or "Suspendido desde CoreX"))
    return JsonResponse({"ok": True, "estado": "suspendido"})


@api(["POST"])
def reactivate(request, data, schema):
    g, err = _gym_or_404(schema)
    if err:
        return err
    _set_status(g, Gym.Status.ACTIVE)
    return JsonResponse({"ok": True, "estado": "activo"})


@api(["POST"])
def plan(request, data, schema):
    g, err = _gym_or_404(schema)
    if err:
        return err
    warnings = _apply_plan(g, data.get("plan"), data.get("limites"))
    return JsonResponse({"ok": True, "advertencias": warnings} if warnings else {"ok": True})
