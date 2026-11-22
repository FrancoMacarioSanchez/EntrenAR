"""Consumo y facturación mensual del plug-in de IA (CoreX → gimnasio).

Cada análisis suma sus tokens en AIUsageMonth (schema público). Durante el mes el consumo viaja al Hub como
métricas diarias (ia_tokens, ia_importe…). El día 1 `close_ai_billing` cierra el período con el precio vigente y
reenvía todos los días del mes con ese precio, así el Hub factura exactamente lo que quedó cerrado acá.
"""
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import AIAddon, AIUsageMonth

log = logging.getLogger(__name__)


def month_start(d=None):
    d = d or timezone.localdate()
    return date(d.year, d.month, 1)


def month_days(month):
    from datetime import timedelta
    nxt = date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)
    return [month + timedelta(days=i) for i in range((nxt - month).days)]


def record_usage(gym, tokens_in, tokens_out):
    """Suma un análisis al mes en curso. Nunca rompe el análisis si algo falla."""
    if not gym or not getattr(gym, "pk", None) or (not tokens_in and not tokens_out):
        return
    try:
        row, _ = AIUsageMonth.objects.get_or_create(gym_id=gym.pk, month=month_start())
        AIUsageMonth.objects.filter(pk=row.pk).update(
            requests=F("requests") + 1, tokens_in=F("tokens_in") + int(tokens_in), tokens_out=F("tokens_out") + int(tokens_out))
    except Exception:  # noqa: BLE001
        log.exception("No se pudo registrar el consumo de IA de %s", gym)


def current_usage(gym):
    return AIUsageMonth.objects.filter(gym_id=gym.pk, month=month_start()).first()


def spent_this_month(addon):
    usage = current_usage(addon.gym)
    return addon.cost_for(usage.tokens) if usage else Decimal("0.00")


def budget_reached(addon):
    return bool(addon.monthly_cap) and spent_this_month(addon) >= addon.monthly_cap


def google_cost_ars(tokens_in, tokens_out):
    """Costo estimado de Google en pesos (para ver el margen de CoreX)."""
    usd = (Decimal(tokens_in) * Decimal(str(settings.GEMINI_PRICE_INPUT_USD))
           + Decimal(tokens_out) * Decimal(str(settings.GEMINI_PRICE_OUTPUT_USD))) / Decimal(1_000_000)
    return (usd * Decimal(str(settings.AI_FX_ARS))).quantize(Decimal("0.01"), ROUND_HALF_UP)


def statement(usage):
    """Resumen de un mes, tal como se manda al Hub."""
    return {
        "concept": "Análisis de comidas con IA (EntrenAR)",
        "period": usage.month.strftime("%Y-%m"),
        "requests": usage.requests,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "tokens": usage.tokens,
        "price_per_1k_tokens": str(usage.price_per_1k_tokens),
        "amount": str(usage.amount),
        "currency": "ARS",
    }


def close_month(month=None, send=True, gyms=None):
    """Cierra los meses abiertos hasta `month` inclusive (por defecto, el mes anterior al actual).

    Congela el precio vigente, calcula el importe y, con `send`, reenvía al Hub las métricas de cada día del mes.
    Devuelve los AIUsageMonth cerrados.
    """
    if month is None:
        first = month_start()
        month = date(first.year - 1, 12, 1) if first.month == 1 else date(first.year, first.month - 1, 1)
    if month >= month_start():
        raise ValueError("Solo se pueden cerrar meses terminados.")
    from .hub_client import hub_enabled, push_metrics

    closed = []
    qs = AIUsageMonth.objects.select_related("gym").filter(status=AIUsageMonth.Status.OPEN, month__lte=month)
    if gyms is not None:
        qs = qs.filter(gym__in=gyms)
    for usage in qs:
        with transaction.atomic():
            usage = AIUsageMonth.objects.select_for_update().get(pk=usage.pk)
            if usage.status != AIUsageMonth.Status.OPEN:
                continue
            addon = AIAddon.for_gym(usage.gym)
            usage.price_per_1k_tokens = addon.price_per_1k_tokens
            usage.amount = addon.cost_for(usage.tokens)
            usage.status = AIUsageMonth.Status.CLOSED
            usage.closed_at = timezone.now()
            usage.save()
        if send and hub_enabled():
            ev = push_metrics(usage.gym, month_days(usage.month), price=usage.price_per_1k_tokens)
            if ev:
                usage.hub_event = str(ev.event_id)
                usage.status = AIUsageMonth.Status.SENT
                usage.save(update_fields=["hub_event", "status"])
            closed.append(usage)
    return closed
