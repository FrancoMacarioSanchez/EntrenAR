"""Complementos del gimnasio: el plug-in «Análisis de comidas con IA»."""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import AuditLog
from apps.members.models import Member
from apps.nutrition.models import AIRequest, NutritionProfile
from apps.tenants.ai_billing import current_usage, month_start, spent_this_month
from apps.tenants.models import AIAddon, AIUsageMonth

from .permissions import perm_required


def _addon(request):
    return AIAddon.for_gym(request.tenant)


@perm_required("settings")
def addons(request):
    addon = _addon(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if not addon.allowed:
            messages.error(request, "CoreX todavía no habilitó este complemento para tu gimnasio.")
            return redirect("panel:addons")
        if action == "activate":
            if not request.POST.get("accept"):
                messages.error(request, "Para activarlo tenés que aceptar el costo por uso.")
                return redirect("panel:addons")
            addon.active = True
            addon.activated_at = timezone.now()
            addon.activated_by = request.user.get_full_name() or request.user.username
            addon.save()
            AuditLog.log(request.user, "settings", "Activó el complemento de análisis de comidas con IA")
            messages.success(request, "Listo: tus alumnos ya pueden analizar sus comidas con IA.")
        elif action == "deactivate":
            addon.active = False
            addon.save()
            AuditLog.log(request.user, "settings", "Desactivó el complemento de análisis de comidas con IA")
            messages.success(request, "Complemento desactivado. Lo consumido este mes se factura igual.")
        elif action == "settings":
            try:
                limit = int(request.POST.get("daily_limit") or 0)
            except ValueError:
                limit = -1
            if not 1 <= limit <= addon.max_daily_limit:
                messages.error(request, f"El límite diario tiene que estar entre 1 y {addon.max_daily_limit}.")
                return redirect("panel:addons")
            cap_raw = (request.POST.get("monthly_cap") or "").strip().replace(".", "").replace(",", ".")
            try:
                cap = Decimal(cap_raw) if cap_raw else None
            except InvalidOperation:
                messages.error(request, "El tope mensual tiene que ser un número.")
                return redirect("panel:addons")
            if cap is not None and cap <= 0:
                cap = None
            addon.daily_limit, addon.monthly_cap = limit, cap
            addon.save()
            AuditLog.log(request.user, "settings", f"IA: límite {limit}/día, tope mensual {cap or 'sin tope'}")
            messages.success(request, "Configuración guardada.")
        return redirect("panel:addons")

    usage = current_usage(request.tenant)
    spent = spent_this_month(addon)
    today = timezone.localdate()
    days_in_month = (date(today.year + (today.month == 12), today.month % 12 + 1, 1) - month_start()).days
    projected = (spent / today.day * days_in_month).quantize(Decimal("0.01")) if spent else Decimal("0.00")
    history = list(AIUsageMonth.objects.filter(gym_id=request.tenant.pk).exclude(month=month_start())[:12])
    for h in history:
        h.shown_amount = h.amount if h.amount is not None else addon.cost_for(h.tokens)
    month_start_dt = timezone.make_aware(datetime.combine(month_start(), time.min))
    top = (AIRequest.objects.filter(created_at__gte=month_start_dt, member__isnull=False)
           .values("member_id", "member__first_name", "member__last_name")
           .annotate(n=Count("id"), tin=Sum("tokens_in"), tout=Sum("tokens_out")).order_by("-n")[:10])
    top = [{**t, "cost": addon.cost_for((t["tin"] or 0) + (t["tout"] or 0))} for t in top]
    custom = (NutritionProfile.objects.filter(ai_daily_limit__isnull=False).select_related("member")
              .order_by("member__first_name"))
    avg_tokens = (usage.tokens // usage.requests) if usage and usage.requests else None
    return render(request, "panel/addons.html", {
        "addon": addon, "usage": usage, "spent": spent, "projected": projected, "history": history, "top": top,
        "custom": custom, "section": "config", "limits": range(1, addon.max_daily_limit + 1),
        "avg_cost": addon.cost_for(avg_tokens) if avg_tokens else None,
        "cap_pct": int(spent / addon.monthly_cap * 100) if addon.monthly_cap else None,
    })


@perm_required("members_edit")
def member_ai_limit(request, pk):
    m = get_object_or_404(Member, pk=pk)
    if request.method == "POST":
        addon = _addon(request)
        raw = request.POST.get("ai_daily_limit", "")
        profile, _ = NutritionProfile.objects.get_or_create(member=m)
        if raw == "":
            profile.ai_daily_limit = None
            text = "el límite del gimnasio"
        else:
            try:
                value = max(0, min(int(raw), addon.max_daily_limit))
            except ValueError:
                messages.error(request, "Valor inválido.")
                return redirect("panel:member_detail", pk=m.pk)
            profile.ai_daily_limit = value
            text = "sin IA" if value == 0 else f"{value} por día"
        profile.save(update_fields=["ai_daily_limit"])
        AuditLog.log(request.user, "members", f"IA de {m.full_name}: {text}")
        messages.success(request, f"Análisis con IA de {m.full_name}: {text}.")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "panel:addons")
