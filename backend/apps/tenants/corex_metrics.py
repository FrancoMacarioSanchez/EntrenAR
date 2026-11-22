"""Métricas diarias de un gimnasio para el CoreX Hub (contrato docs/API_SAAS.md del Hub).

`collect(gym, day)` corre dentro del schema del gimnasio y devuelve {clave: número}.
Contadores = lo que pasó ese día. Niveles = valor en ese momento (solo se informan para hoy y ayer,
salvo `socios_activos`, que se reconstruye por fecha a partir de las membresías).
"""
from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.models import Count, Sum
from django.utils import timezone

# clave, nombre, unidad, tipo, visible para el cliente, destacada en el panel dev  (para `corex_setup entrenar`)
CATALOG = [
    ("socios_activos", "Socios activos", "", "nivel", True, True),
    ("socios_total", "Socios registrados", "", "nivel", True, False),
    ("usuarios_staff", "Usuarios del staff", "", "nivel", True, False),
    ("app_usuarios", "Alumnos con la app", "", "nivel", True, False),
    ("ingresos", "Ingresos al gimnasio", "", "contador", True, True),
    ("cobros_cantidad", "Cobros", "", "contador", True, False),
    ("cobros_monto", "Monto cobrado", "$", "contador", True, True),
    ("membresias_vendidas", "Membresías vendidas", "", "contador", True, False),
    ("entrenamientos", "Entrenamientos registrados", "", "contador", True, False),
    ("leads_nuevos", "Leads nuevos", "", "contador", True, False),
    ("ia_analisis", "Análisis de comidas con IA", "", "contador", True, True),
    ("ia_tokens", "Tokens de IA", "tokens", "contador", True, True),
    ("ia_tokens_entrada", "Tokens de IA (entrada)", "tokens", "contador", False, False),
    ("ia_tokens_salida", "Tokens de IA (salida)", "tokens", "contador", False, False),
    ("ia_importe", "Consumo de IA a facturar", "$", "contador", True, True),
    ("ia_costo_google", "Costo de Google (estimado)", "$", "contador", False, False),
    ("db_mb", "Tamaño de la base", "MB", "nivel", False, True),
]


def schema_size_mb(schema):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(pg_total_relation_size(format('%%I.%%I', schemaname, tablename))), 0) "
            "FROM pg_tables WHERE schemaname = %s", [schema])
        size = cur.fetchone()[0] or 0
    return round(size / 1024 / 1024, 2)


def collect(gym, day, price=None):
    """Llamar dentro de tenant_context(gym). `price` fija el precio por 1.000 tokens (cierre de mes)."""
    from apps.accounts.models import User
    from apps.billing.models import Payment
    from apps.crm.models import Lead
    from apps.members.models import Member
    from apps.memberships.models import CheckIn, Membership
    from apps.nutrition.models import AIRequest
    from apps.training.models import WorkoutSession

    from .ai_billing import google_cost_ars
    from .models import AIAddon

    pays = Payment.objects.filter(is_void=False, paid_at__date=day).aggregate(n=Count("id"), s=Sum("amount"))
    ai = (AIRequest.objects.filter(created_at__date=day).exclude(status=AIRequest.Status.ERROR)
          .aggregate(n=Count("id"), tin=Sum("tokens_in"), tout=Sum("tokens_out")))
    tin, tout = int(ai["tin"] or 0), int(ai["tout"] or 0)
    addon = AIAddon.objects.filter(gym_id=gym.pk).first()
    if price is None:
        price = addon.price_per_1k_tokens if addon else Decimal("0")
    data = {
        "socios_activos": (Membership.objects.filter(start_date__lte=day, end_date__gte=day)
                           .exclude(status=Membership.Status.CANCELLED).values("member").distinct().count()),
        "ingresos": CheckIn.objects.filter(allowed=True, created_at__date=day).count(),
        "cobros_cantidad": pays["n"] or 0,
        "cobros_monto": float(pays["s"] or 0),
        "membresias_vendidas": Membership.objects.filter(created_at__date=day).count(),
        "entrenamientos": WorkoutSession.objects.filter(date=day).count(),
        "leads_nuevos": Lead.objects.filter(created_at__date=day).count(),
        "ia_analisis": ai["n"] or 0,
        "ia_tokens": tin + tout,
        "ia_tokens_entrada": tin,
        "ia_tokens_salida": tout,
        "ia_importe": float((Decimal(tin + tout) / 1000 * price).quantize(Decimal("0.01"))),
        "ia_costo_google": float(google_cost_ars(tin, tout)),
    }
    if day >= timezone.localdate() - timedelta(days=1):  # niveles: solo el valor actual
        data.update({
            "socios_total": Member.objects.count(),
            "usuarios_staff": User.objects.exclude(role=User.Role.STUDENT).filter(is_active=True, is_support=False).count(),
            "app_usuarios": User.objects.filter(role=User.Role.STUDENT, is_active=True).count(),
            "db_mb": schema_size_mb(gym.schema_name),
        })
    return data
