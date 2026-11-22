"""Sección «Costos y facturación» del admin de CoreX (/corex-admin/costos/)."""
import csv
from datetime import date

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render

from . import costs
from .ai_billing import month_start
from .hub_client import hub_enabled, queue_health


def _parse_month(value):
    try:
        y, m = (int(x) for x in (value or "").split("-")[:2])
        return date(y, m, 1)
    except (TypeError, ValueError):
        return month_start()


def costs_view(request):
    month = _parse_month(request.GET.get("mes"))
    report = costs.month_report(month)
    if request.GET.get("csv"):
        return _csv(report)
    ctx = {
        **admin.site.each_context(request),
        "title": "Costos y facturación",
        "report": report, "t": report["totals"],
        "months": costs.prev_months(12)[::-1], "series": costs.series(6),
        "hub": {"enabled": hub_enabled(), **queue_health()},
        "gemini": {"model": settings.GEMINI_MODEL, "in": settings.GEMINI_PRICE_INPUT_USD,
                   "out": settings.GEMINI_PRICE_OUTPUT_USD, "fx": settings.AI_FX_ARS},
    }
    return render(request, "admin/costs.html", ctx)


def _csv(report):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="entrenar_costos_{report["month"]:%Y-%m}.csv"'
    resp.write("﻿")
    w = csv.writer(resp, delimiter=";")
    num = lambda v: str(v).replace(".", ",")  # noqa: E731
    w.writerow(["Gimnasio", "Schema", "CUIT", "Estado", "Plan", "Abono", "Análisis IA", "Tokens", "IA a facturar",
                "IA estimado", "Costo Google", "Margen IA", "Total a facturar"])
    for r in report["rows"]:
        g = r["gym"]
        w.writerow([g.name, g.schema_name, g.cuit, r["state"], r["plan"].name if r["plan"] else "", num(r["plan_fee"]),
                    r["requests"], r["tokens"], num(r["ai_billed"]), "sí" if r["ai_estimated"] else "no",
                    num(r["google"]), num(r["ai_margin"]), num(r["total"])])
    w.writerow([])
    w.writerow(["Costos fijos", "", "", "", "", "", "", "", "", "", num(report["totals"]["infra"])])
    w.writerow(["Resultado", "", "", "", "", "", "", "", "", "", "", "", num(report["totals"]["result"])])
    return resp
