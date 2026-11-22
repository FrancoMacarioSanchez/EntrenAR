"""Panel del gimnasio: login, dashboard, configuración, suscripción, reportes y cuenta."""
import csv
import io
import zipfile
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.billing.models import Expense, Payment
from apps.core.models import AuditLog, GymSettings, Notification
from apps.core.stats import dashboard_data
from apps.memberships.models import CheckIn, Membership

from .forms import GymSettingsForm
from .forms_utils import style_widget
from .permissions import perm_required, staff_required


# ------------------------------------------------------------------ auth
def login_view(request):
    if request.user.is_authenticated:
        return redirect("panel:home")
    form = AuthenticationForm(request, data=request.POST or None)
    for f in form.fields.values():
        style_widget(f)
    form.fields["username"].label = "Usuario, email o DNI"
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        AuditLog.log(user, "login", "Ingreso al panel")
        if user.is_trainer or user.is_student:
            return redirect("/app/")
        return redirect(request.GET.get("next") or "panel:home")
    return render(request, "panel/login.html", {"form": form, "activated": request.GET.get("activada")})


def activate_account(request, uidb64, token):
    """Link de invitación: el dueño define su contraseña (alta desde CoreX Hub)."""
    from django.contrib.auth import views as auth_views
    from django.contrib.auth.forms import SetPasswordForm

    class StyledSetPasswordForm(SetPasswordForm):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            for f in self.fields.values():
                style_widget(f)

    view = auth_views.PasswordResetConfirmView.as_view(
        template_name="panel/activate.html", success_url="/login/?activada=1", post_reset_login=False,
        form_class=StyledSetPasswordForm)
    return view(request, uidb64=uidb64, token=token)


def logout_view(request):
    logout(request)
    return redirect("panel:login")


def home(request):
    if not request.user.is_authenticated:
        return redirect("panel:login")
    if request.user.is_trainer or request.user.is_student:
        return redirect("/app/")
    return dashboard(request)


@staff_required
def dashboard(request):
    data = dashboard_data()
    rmax = max((m["value"] for m in data["revenue_series"]), default=0) or 1
    gmax = max((m["value"] for m in data["growth_series"]), default=0) or 1
    hours = list(range(6, 23))
    hmax = max((max(r[6:23]) for r in data["heatmap"]), default=0) or 1
    days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    heat = [{"day": days[i], "cells": [{"h": h, "v": row[h], "o": round(0.08 + 0.92 * row[h] / hmax, 2) if row[h] else 0}
                                       for h in hours]} for i, row in enumerate(data["heatmap"])]
    for m in data["revenue_series"]:
        m["pct"] = max(round(m["value"] / rmax * 100), 2)
    for m in data["growth_series"]:
        m["pct"] = max(round(m["value"] / gmax * 100), 2)
    total_mix = sum(p["c"] for p in data["plan_mix"]) or 1
    for p in data["plan_mix"]:
        p["pct"] = round(p["c"] / total_mix * 100)
    return render(request, "panel/dashboard.html", {"d": data, "heat": heat, "hours": hours, "section": "dashboard",
                                                    "greeting": _greeting()})


def _greeting():
    h = timezone.localtime().hour
    return "Buen día" if h < 13 else ("Buenas tardes" if h < 20 else "Buenas noches")


# ------------------------------------------------------------------ configuración
@perm_required('settings')
def settings_view(request):
    obj = GymSettings.get()
    form = GymSettingsForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.log(request.user, "settings", "Actualizó la configuración")
        messages.success(request, "Configuración guardada.")
        return redirect("panel:settings")
    groups = [
        ("Identidad", ["display_name", "logo", "primary_color", "accent_color", "address", "phone", "whatsapp",
                       "email", "instagram", "opening_hours", "welcome_message"]),
        ("Reglas de negocio", ["enrollment_fee", "late_fee_percent", "late_fee_after_days", "access_grace_days",
                               "block_access_with_debt", "require_medical_clearance", "auto_renew_default",
                               "expiry_notice_days", "inactivity_alert_days", "trainers_see_all_members",
                               "students_can_edit_routine"]),
        ("Ingreso con QR (autoservicio)", ["self_checkin_enabled", "checkin_require_location", "latitude", "longitude",
                                           "checkin_radius_m"]),
        ("Mercado Pago", ["mp_access_token", "mp_public_key"]),
        ("Facturación electrónica (ARCA)", ["arca_enabled", "arca_webhook_url", "arca_webhook_token",
                                            "arca_point_of_sale", "arca_invoice_type"]),
    ]
    return render(request, "panel/settings.html", {
        "form": form, "groups": [(t, [form[f] for f in fs]) for t, fs in groups], "section": "config",
        "mp_webhook": request.build_absolute_uri("/webhooks/mercadopago/"),
    })


def subscription(request):
    if not request.user.is_authenticated:
        return redirect("panel:login")
    from django.conf import settings

    from apps.tenants.models import Gym, SaasPlan

    gym = Gym.objects.select_related("plan").get(schema_name=request.tenant.schema_name)
    from apps.crm.services import active_members
    from apps.tenants.ai_billing import current_usage
    from apps.tenants.models import AIAddon, AIUsageMonth

    addon = AIAddon.for_gym(gym)
    usage = current_usage(gym)
    spent = addon.cost_for(usage.tokens) if usage else 0
    history = []
    for u in AIUsageMonth.objects.filter(gym=gym).order_by("-month")[:12]:
        history.append({"u": u, "amount": u.amount if u.amount is not None else addon.cost_for(u.tokens)})
    return render(request, "panel/subscription.html", {
        "gym": gym, "plans": SaasPlan.objects.filter(is_active=True), "portal_url": settings.HUB_PORTAL_URL,
        "active_members": active_members().count(), "section": "config",
        "addon": addon, "usage": usage, "ai_spent": spent, "ai_history": history,
        "estimated_total": (gym.plan.price_monthly if gym.plan else 0) + spent,
    })


# ------------------------------------------------------------------ reportes
@perm_required('reports')
def reports(request):
    today = timezone.localdate()
    d_from = parse_date(request.GET.get("from", "")) or today.replace(day=1)
    d_to = parse_date(request.GET.get("to", "")) or today
    pays = Payment.objects.filter(is_void=False, paid_at__date__gte=d_from, paid_at__date__lte=d_to)
    exps = Expense.objects.filter(date__gte=d_from, date__lte=d_to)
    income = pays.aggregate(s=Sum("amount"))["s"] or 0
    expenses = exps.aggregate(s=Sum("amount"))["s"] or 0
    by_method = pays.values("method__name").annotate(t=Sum("amount"), c=Count("id")).order_by("-t")
    by_kind = pays.values("charge__kind").annotate(t=Sum("amount")).order_by("-t")
    by_plan = (Membership.objects.filter(created_at__date__gte=d_from, created_at__date__lte=d_to)
               .values("plan__name").annotate(c=Count("id"), t=Sum("price")).order_by("-c"))
    by_cat = exps.values("category").annotate(t=Sum("amount")).order_by("-t")
    cat_labels = dict(Expense.Category.choices)
    checkins = CheckIn.objects.filter(allowed=True, created_at__date__gte=d_from, created_at__date__lte=d_to)
    by_day = {}
    for c in checkins.values_list("created_at", flat=True):
        k = timezone.localtime(c).date()
        by_day[k] = by_day.get(k, 0) + 1
    days, d = [], d_from
    while d <= d_to:
        days.append({"label": d.strftime("%d/%m"), "value": by_day.get(d, 0)})
        d += timedelta(days=1)
    from apps.billing.models import Charge

    kind_labels = dict(Charge.Kind.choices)
    if request.GET.get("export") == "pagos":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="pagos_{d_from}_{d_to}.csv"'
        resp.write("﻿")
        w = csv.writer(resp, delimiter=";")
        w.writerow(["Fecha", "Socio", "DNI", "Concepto", "Medio", "Importe", "Factura", "CAE"])
        for p in pays.select_related("member", "method", "charge"):
            w.writerow([timezone.localtime(p.paid_at).strftime("%d/%m/%Y %H:%M"), p.member.full_name, p.member.dni or "",
                        p.charge.concept if p.charge else p.notes, p.method.name, str(p.amount).replace(".", ","),
                        p.invoice_number, p.invoice_cae])
        return resp
    return render(request, "panel/reports.html", {
        "d_from": d_from, "d_to": d_to, "income": income, "expenses": expenses, "net": income - expenses,
        "by_method": by_method, "by_plan": by_plan, "checkins_total": checkins.count(), "days": days,
        "by_kind": [{"label": kind_labels.get(r["charge__kind"], "Pago a cuenta"), "t": r["t"]} for r in by_kind],
        "by_cat": [{"label": cat_labels.get(r["category"], r["category"]), "t": r["t"]} for r in by_cat],
        "section": "finanzas",
    })


@perm_required('audit')
def audit(request):
    logs = AuditLog.objects.select_related("user")[:300]
    return render(request, "panel/audit.html", {"logs": logs, "section": "config"})


# ------------------------------------------------------------------ cuenta
def password_change(request):
    if not request.user.is_authenticated:
        return redirect("panel:login")
    form = PasswordChangeForm(request.user, request.POST or None)
    for f in form.fields.values():
        style_widget(f)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Contraseña actualizada.")
        return redirect("panel:home")
    return render(request, "panel/password.html", {"form": form})


@perm_required('export')
def export_all(request):
    """Exporta todos los datos del gimnasio en un ZIP de CSVs."""
    from apps.billing.models import Charge
    from apps.body.models import BodyMeasurement
    from apps.crm.models import Lead
    from apps.members.models import Member

    sets = {
        "socios.csv": (Member.objects.all(), ["id", "first_name", "last_name", "dni", "email", "phone", "birth_date",
                                              "sex", "status", "joined_at"]),
        "membresias.csv": (Membership.objects.all(), ["id", "member_id", "plan__name", "start_date", "end_date",
                                                      "price", "discount_percent", "status"]),
        "cargos.csv": (Charge.objects.all(), ["id", "member_id", "concept", "kind", "amount", "due_date", "status"]),
        "pagos.csv": (Payment.objects.all(), ["id", "member_id", "charge_id", "amount", "method__name", "paid_at",
                                              "is_void", "invoice_number"]),
        "ingresos.csv": (CheckIn.objects.all(), ["id", "member_id", "created_at", "allowed", "reason"]),
        "mediciones.csv": (BodyMeasurement.objects.all(), ["id", "member_id", "date", "weight_kg", "body_fat",
                                                           "waist", "hip", "neck"]),
        "leads.csv": (Lead.objects.all(), ["id", "name", "phone", "email", "source", "stage", "created_at"]),
        "gastos.csv": (Expense.objects.all(), ["id", "date", "category", "description", "amount"]),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, (qs, cols) in sets.items():
            s = io.StringIO()
            w = csv.writer(s, delimiter=";")
            w.writerow(cols)
            for row in qs.values_list(*cols):
                w.writerow(["" if v is None else v for v in row])
            z.writestr(name, "﻿" + s.getvalue())
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="entrenar_{request.tenant.slug}_{timezone.localdate()}.zip"'
    return resp


@staff_required
def notifications(request):
    qs = Notification.objects.filter(user=request.user)[:50]
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, "panel/notifications.html", {"items": qs})


@require_POST
@perm_required('members_view')
def global_search(request):
    return redirect(f"/socios/?q={request.POST.get('q', '')}")


@perm_required("management")
def management(request):
    from apps.core.analytics import management_data

    try:
        months = int(request.GET.get("meses", 12))
    except ValueError:
        months = 12
    months = months if months in (6, 12, 24) else 12
    data = management_data(months)
    return render(request, "panel/management.html", {"m": data, "k": data["kpis"], "months": months,
                                                     "section": "gerencia"})
