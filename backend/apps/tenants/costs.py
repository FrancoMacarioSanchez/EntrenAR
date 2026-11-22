"""Costos y facturación de EntrenAR para CoreX: cuánto se factura, cuánto cuesta y cuánto queda, por mes."""
from collections import OrderedDict
from datetime import date
from decimal import Decimal

from django.conf import settings

from .ai_billing import google_cost_ars, month_start
from .models import AIAddon, AIUsageMonth, Gym, InfraCost

ZERO = Decimal("0.00")
BILLABLE = (Gym.Status.ACTIVE, Gym.Status.PAST_DUE)


def prev_months(n, until=None):
    m = month_start(until)
    out = []
    for _ in range(n):
        out.append(m)
        m = date(m.year - 1, 12, 1) if m.month == 1 else date(m.year, m.month - 1, 1)
    return out[::-1]


def _pct(part, total):
    return round(part / total * 100) if total else None


def month_report(month):
    """Reporte de un mes (month = primer día). Para el mes en curso, los importes de IA son estimados."""
    current = month == month_start()
    gyms = list(Gym.objects.exclude(schema_name=settings.PUBLIC_SCHEMA_NAME).select_related("plan").order_by("name"))
    usage = {u.gym_id: u for u in AIUsageMonth.objects.filter(month=month)}
    addons = {a.gym_id: a for a in AIAddon.objects.all()}

    rows = []
    for g in gyms:
        u = usage.get(g.pk)
        addon = addons.get(g.pk)
        tokens_in, tokens_out = (u.tokens_in, u.tokens_out) if u else (0, 0)
        if u and u.amount is not None:
            ai_billed, estimated = u.amount, False
        else:
            ai_billed = addon.cost_for(tokens_in + tokens_out) if addon else ZERO
            estimated = bool(u)
        google = google_cost_ars(tokens_in, tokens_out)
        plan_fee = (g.plan.price_monthly if g.plan and g.status in BILLABLE and g.created_at.date() < _next(month)
                    else ZERO)
        rows.append({
            "gym": g, "plan": g.plan, "state": g.effective_state, "plan_fee": plan_fee,
            "ai_enabled": bool(addon and addon.enabled), "ai_price": addon.price_per_1k_tokens if addon else None,
            "requests": u.requests if u else 0, "tokens": tokens_in + tokens_out, "tokens_in": tokens_in,
            "tokens_out": tokens_out, "ai_billed": ai_billed, "ai_estimated": estimated,
            "ai_status": u.get_status_display() if u else "—", "google": google,
            "ai_margin": ai_billed - google, "ai_margin_pct": _pct(ai_billed - google, ai_billed),
            "total": plan_fee + ai_billed,
        })

    infra = [c for c in InfraCost.objects.all() if c.applies_to(month)]
    infra_rows = [{"cost": c, "ars": c.monthly_ars()} for c in infra]
    t = {k: sum((r[k] for r in rows), ZERO) for k in ("plan_fee", "ai_billed", "google", "total")}
    t["tokens"] = sum(r["tokens"] for r in rows)
    t["requests"] = sum(r["requests"] for r in rows)
    t["infra"] = sum((r["ars"] for r in infra_rows), ZERO)
    t["costs"] = t["google"] + t["infra"]
    t["result"] = t["total"] - t["costs"]
    t["result_pct"] = _pct(t["result"], t["total"])
    t["ai_margin"] = t["ai_billed"] - t["google"]
    t["ai_margin_pct"] = _pct(t["ai_margin"], t["ai_billed"])
    paying = [r for r in rows if r["plan_fee"]]
    t["paying"] = len(paying)
    t["cost_per_gym"] = (t["costs"] / len(paying)).quantize(Decimal("0.01")) if paying else None
    return {"month": month, "current": current, "rows": rows, "infra": infra_rows, "totals": t,
            "pending_close": [r for r in rows if r["ai_estimated"] and not current]}


def _next(month):
    return date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)


def series(n=6):
    """Totales de los últimos n meses (para el gráfico)."""
    out = OrderedDict()
    for m in prev_months(n):
        t = month_report(m)["totals"]
        out[m] = {"month": m, "income": t["total"], "costs": t["costs"], "result": t["result"],
                  "ai_billed": t["ai_billed"], "google": t["google"]}
    top = max([max(v["income"], v["costs"]) for v in out.values()] + [Decimal("1")])
    for v in out.values():
        v["income_h"] = int(v["income"] / top * 100)
        v["costs_h"] = int(v["costs"] / top * 100)
    return list(out.values())
