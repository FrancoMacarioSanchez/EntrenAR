"""Totales diarios, promedios semanales, racha y adherencia (semáforo para el entrenador)."""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import MealLog, MealLogItem

MACROS = ("kcal", "protein", "carbs", "fat", "fiber")


def daily_totals(member, start, end):
    """{fecha: {kcal, protein, carbs, fat, fiber}} solo para los días con algo registrado."""
    rows = (MealLogItem.objects.filter(meal__member=member, meal__date__gte=start, meal__date__lte=end)
            .values("meal__date").annotate(**{k: Sum(k) for k in MACROS}))
    return {r["meal__date"]: {k: round(float(r[k] or 0), 1) for k in MACROS} for r in rows}


def streak(member, today=None):
    """Días seguidos con al menos una comida registrada (cuenta hasta hoy, o hasta ayer si hoy todavía no cargó)."""
    today = today or timezone.localdate()
    dates = set(MealLog.objects.filter(member=member, date__gte=today - timedelta(days=400), date__lte=today)
                .values_list("date", flat=True))
    day = today if today in dates else today - timedelta(days=1)
    n = 0
    while day in dates:
        n += 1
        day -= timedelta(days=1)
    return n


def day_status(total, targets):
    """ok: calorías ±10 % y proteína ≥ 90 % · mid: cumple una de las dos · bad: ninguna · None: sin registro."""
    if not total:
        return None
    if not targets:
        return "logged"
    kcal_ok = abs(total["kcal"] - targets["kcal"]) <= targets["kcal"] * 0.10
    prot_ok = not targets["protein"] or total["protein"] >= targets["protein"] * 0.9
    return "ok" if kcal_ok and prot_ok else "mid" if kcal_ok or prot_ok else "bad"


def adherence(member, targets, days=7, today=None):
    """Resumen de los últimos `days` días completos (sin contar hoy) + color del semáforo."""
    today = today or timezone.localdate()
    end, start = today - timedelta(days=1), today - timedelta(days=days)
    totals = daily_totals(member, start, end)
    statuses = [day_status(totals.get(start + timedelta(days=i)), targets) for i in range(days)]
    logged = [t for t in totals.values()]
    ok = statuses.count("ok")
    n = len(logged)
    avg = {k: round(sum(t[k] for t in logged) / n, 1) for k in MACROS} if n else None
    if n >= 5 and (not targets or ok >= 4):
        color = "green"
    elif n >= 3:
        color = "yellow"
    else:
        color = "red"
    return {"days": days, "days_logged": n, "days_ok": ok, "statuses": statuses, "avg": avg, "color": color,
            "protein_pct": round(avg["protein"] / targets["protein"] * 100) if avg and targets and targets["protein"] else None,
            "kcal_pct": round(avg["kcal"] / targets["kcal"] * 100) if avg and targets and targets["kcal"] else None}


def series(member, days=30, targets=None, today=None):
    today = today or timezone.localdate()
    start = today - timedelta(days=days - 1)
    totals = daily_totals(member, start, today)
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        t = totals.get(d)
        out.append({"date": d, **(t or {k: None for k in MACROS}), "status": day_status(t, targets)})
    weeks = []
    for i in range(0, days, 7):
        chunk = [x for x in out[i:i + 7] if x["kcal"] is not None]
        if chunk:
            weeks.append({"start": out[i]["date"], "days_logged": len(chunk),
                          "avg_kcal": round(sum(x["kcal"] for x in chunk) / len(chunk)),
                          "avg_protein": round(sum(x["protein"] for x in chunk) / len(chunk))})
    weight = list(member.measurements.filter(date__gte=start, weight_kg__isnull=False).order_by("date")
                  .values("date", "weight_kg"))
    return {"days": out, "weeks": weeks,
            "weight": [{"date": w["date"], "weight": float(w["weight_kg"])} for w in weight]}
