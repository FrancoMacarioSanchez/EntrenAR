"""Socios (ficha 360) y membresías."""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.billing.models import Charge
from apps.core.models import AuditLog
from apps.core.utils import wa_link
from apps.members.models import Member, MemberNote
from apps.members.services import ensure_app_access
from apps.memberships.models import Membership, Plan
from apps.memberships.services import freeze, renew, sell_membership

from .forms import FreezeForm, MemberForm, NoteForm, PaymentForm, SellMembershipForm
from .permissions import perm_required

STATE_LABELS = {"active": ("Al día", "ok"), "expiring": ("Por vencer", "warn"), "grace": ("Vencida (tolerancia)", "warn"),
                "expired": ("Vencida", "bad"), "frozen": ("Congelada", "info"), "none": ("Sin plan", "muted")}


def _check_plan_limit(request):
    from apps.crm.services import active_members
    from apps.tenants.models import Gym

    gym = Gym.objects.select_related("plan").get(schema_name=request.tenant.schema_name)
    if gym.max_members and active_members().count() >= gym.max_members:
        messages.warning(request, f"Llegaste a {gym.max_members} socios activos, el máximo de tu plan "
                                  f"{gym.plan.name}. Mejorá el plan desde «Suscripción».")


@perm_required('members_view')
def member_list(request):
    qs = Member.objects.select_related("trainer").annotate(last_end=Max("memberships__end_date"))
    q = request.GET.get("q", "").strip()
    if q:
        for token in q.split():
            qs = qs.filter(Q(first_name__icontains=token) | Q(last_name__icontains=token) | Q(dni__icontains=token)
                           | Q(email__icontains=token) | Q(phone__icontains=token))
    today = timezone.localdate()
    state = request.GET.get("state", "")
    if state == "active":
        qs = qs.filter(last_end__gte=today)
    elif state == "expiring":
        qs = qs.filter(last_end__gte=today, last_end__lte=today + timedelta(days=7))
    elif state == "expired":
        qs = qs.filter(last_end__lt=today)
    elif state == "none":
        qs = qs.filter(last_end__isnull=True)
    elif state == "debt":
        qs = qs.filter(charges__status__in=["pending", "partial"], charges__due_date__lte=today).distinct()
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("trainer"):
        qs = qs.filter(trainer_id=request.GET["trainer"])
    order = request.GET.get("order", "last_name")
    if order in ("last_name", "-joined_at", "last_end", "-last_end"):
        qs = qs.order_by(order, "first_name")
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    rows = []
    for m in page:
        st, mem = m.membership_state()
        rows.append({"m": m, "state": STATE_LABELS[st], "membership": mem})
    params = request.GET.copy()
    params.pop("page", None)
    ctx = {"rows": rows, "page": page, "q": q, "state": state, "querystring": params.urlencode(),
           "trainers": User.objects.filter(role="trainer"), "section": "socios", "total": qs.count()}
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "member-table":
        return render(request, "panel/members/_table.html", ctx)
    return render(request, "panel/members/list.html", ctx)


@perm_required('members_edit')
def member_form(request, pk=None):
    member = get_object_or_404(Member, pk=pk) if pk else None
    form = MemberForm(request.POST or None, request.FILES or None, instance=member)
    if request.method == "POST" and form.is_valid():
        m = form.save()
        AuditLog.log(request.user, "member", f"{'Editó' if member else 'Alta de'} socio {m}")
        if not member:
            _check_plan_limit(request)
            if form.cleaned_data.get("create_app_access"):
                user, pwd = ensure_app_access(m)
                messages.info(request, f"Acceso a la app: usuario «{user.username}», contraseña «{pwd}».")
            messages.success(request, f"{m.full_name} fue dado de alta. Ahora vendele una membresía.")
            return redirect(f"/membresias/vender/?member={m.pk}")
        messages.success(request, "Datos guardados.")
        return redirect("panel:member_detail", pk=m.pk)
    return render(request, "panel/members/form.html", {"form": form, "member": member, "section": "socios"})


@perm_required('members_view')
def member_detail(request, pk):
    m = get_object_or_404(Member.objects.select_related("trainer", "user"), pk=pk)
    tab = request.GET.get("tab", "resumen")
    st, mem = m.membership_state()
    ctx = {"m": m, "tab": tab, "state": STATE_LABELS[st], "state_code": st, "membership": mem,
           "section": "socios", "wa": wa_link(m.phone), "note_form": NoteForm(), "pay_form": PaymentForm()}
    if tab == "resumen":
        from apps.training.models import PersonalRecord

        ctx.update(
            visits_30=m.checkins.filter(allowed=True, created_at__gte=timezone.now() - timedelta(days=30)).count(),
            pending=Charge.objects.filter(member=m, status__in=["pending", "partial"]),
            notes=m.member_notes.select_related("author")[:10],
            last_measure=m.measurements.first(), routine=m.routines.filter(is_active=True).first(),
            prs=PersonalRecord.objects.filter(member=m).select_related("exercise")[:5],
            sessions_30=m.sessions.filter(date__gte=timezone.localdate() - timedelta(days=30)).count(),
        )
        from apps.nutrition.models import AIRequest, NutritionProfile
        from apps.tenants.models import AIAddon

        addon = AIAddon.for_gym(request.tenant)
        if addon and addon.enabled:
            own = NutritionProfile.objects.filter(member=m).values_list("ai_daily_limit", flat=True).first()
            first = timezone.localdate().replace(day=1)
            ctx.update(ai_addon=addon, ai_own_limit=own, ai_options=range(0, addon.max_daily_limit + 1),
                       ai_month=AIRequest.objects.filter(member=m, created_at__date__gte=first).count())
    elif tab == "membresias":
        ctx["memberships"] = m.memberships.select_related("plan").prefetch_related("freezes")
        ctx["freeze_form"] = FreezeForm()
    elif tab == "cobros":
        ctx["charges"] = m.charges.all()[:100]
        ctx["payments"] = m.payments.select_related("method", "charge", "received_by")[:100]
    elif tab == "ingresos":
        ctx["checkins"] = m.checkins.select_related("by")[:200]
        ctx["bookings"] = m.bookings.select_related("gym_class")[:50]
    elif tab == "entrenamiento":
        ctx["routines"] = m.routines.prefetch_related("days__exercises__exercise")[:10]
        ctx["sessions"] = m.sessions.prefetch_related("sets__exercise").select_related("routine_day")[:15]
        ctx["records"] = m.records.select_related("exercise")[:30]
        ctx["achievements"] = m.achievements.all()
    elif tab == "medidas":
        ctx["measurements"] = m.measurements.all()[:30]
        ctx["photos"] = m.photos.all()[:30]
    return render(request, "panel/members/detail.html", ctx)


@require_POST
@perm_required('members_view')
def member_note(request, pk):
    m = get_object_or_404(Member, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        MemberNote.objects.create(member=m, author=request.user, **form.cleaned_data)
    return redirect("panel:member_detail", pk=pk)


@require_POST
@perm_required('app_access')
def member_app_access(request, pk):
    m = get_object_or_404(Member, pk=pk)
    if m.user:
        import secrets

        pwd = m.dni or secrets.token_urlsafe(6)
        m.user.set_password(pwd)
        m.user.must_change_password = True
        m.user.is_active = True
        m.user.save()
        messages.success(request, f"Contraseña reseteada. Usuario «{m.user.username}», contraseña «{pwd}».")
    else:
        user, pwd = ensure_app_access(m)
        messages.success(request, f"Acceso creado. Usuario «{user.username}», contraseña «{pwd}».")
    AuditLog.log(request.user, "app_access", f"Acceso a la app de {m}")
    return redirect("panel:member_detail", pk=pk)


@perm_required('members_delete')
def member_delete(request, pk):
    m = get_object_or_404(Member, pk=pk)
    if request.method == "POST":
        name = m.full_name
        if m.user:
            m.user.delete()
        m.delete()
        AuditLog.log(request.user, "delete", f"Eliminó al socio {name}")
        messages.success(request, f"{name} fue eliminado.")
        return redirect("panel:members")
    return render(request, "panel/crud/confirm_delete.html", {
        "obj": m, "crud": {"title": "Socio", "title_plural": "Socios"}, "list_url": "/socios/",
        "warning": "Se borran también sus membresías, pagos, rutinas, entrenamientos y mediciones. "
                   "Si solo dejó de venir, mejor cambiá su estado a «Inactivo»."})


@perm_required('members_view', 'checkin')
def member_card(request, pk):
    m = get_object_or_404(Member, pk=pk)
    return render(request, "panel/members/card.html", {"m": m})


@perm_required('members_view', 'sell', 'collect', 'checkin')
def member_search_json(request):
    from django.http import JsonResponse

    q = request.GET.get("q", "").strip()
    qs = Member.objects.all()
    for token in q.split():
        qs = qs.filter(Q(first_name__icontains=token) | Q(last_name__icontains=token) | Q(dni__icontains=token))
    return JsonResponse({"results": [{"id": m.pk, "text": f"{m.full_name} · {m.dni or 's/DNI'}"} for m in qs[:15]]})


# ------------------------------------------------------------------ membresías
@perm_required('sell')
def sell(request):
    initial = {}
    member = None
    if request.GET.get("member"):
        member = Member.objects.filter(pk=request.GET["member"]).first()
        initial["member"] = member
        if member and member.memberships.count() == 0:
            initial["charge_enrollment"] = True
    if request.GET.get("plan"):
        initial["plan"] = request.GET["plan"]
    form = SellMembershipForm(request.POST or None, initial=initial, user=request.user)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        m, charges, payments = sell_membership(
            d["member"], d["plan"], start_date=d["start_date"], discount_percent=d.get("discount_percent") or 0,
            user=request.user, auto_renew=d["auto_renew"], charge_enrollment=d["charge_enrollment"],
            pay_method=d["pay_method"] if d["pay_now"] else None, pay_amount=d["pay_amount"], notes=d["notes"],
            promotion=d.get("promotion"))
        AuditLog.log(request.user, "membership", f"Vendió {m}")
        messages.success(request, f"Membresía registrada: {m.plan.name} hasta el {m.end_date:%d/%m/%Y}.")
        if payments:
            return redirect("panel:receipt", pk=payments[0].pk)
        return redirect("panel:member_detail", pk=m.member_id)
    plans = Plan.objects.filter(is_active=True)
    promos = []
    if "promotion" in form.fields:
        for p in form.fields["promotion"].queryset.prefetch_related("plans"):
            if p.is_current():
                promos.append({"id": p.pk, "name": p.name, "kind": p.kind, "value": float(p.value), "summary": p.summary,
                               "plans": [x.pk for x in p.plans.all()], "code": p.code, "color": p.color,
                               "only_new": p.only_new_members})
    return render(request, "panel/memberships/sell.html", {
        "form": form, "member": member, "plans": plans, "promos": promos, "section": "recepcion"})


@require_POST
@perm_required('freeze')
def membership_freeze(request, pk):
    m = get_object_or_404(Membership, pk=pk)
    form = FreezeForm(request.POST)
    if form.is_valid():
        try:
            f = freeze(m, user=request.user, **form.cleaned_data)
            messages.success(request, f"Membresía congelada {f.days} días. Nuevo vencimiento: {m.end_date:%d/%m/%Y}.")
            AuditLog.log(request.user, "freeze", f"Congeló {m} ({f.days} días)")
        except ValueError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Revisá las fechas del congelamiento.")
    return redirect(f"/socios/{m.member_id}/?tab=membresias")


@require_POST
@perm_required('sell')
def membership_renew(request, pk):
    m = get_object_or_404(Membership, pk=pk)
    new = renew(m, user=request.user)
    if new:
        messages.success(request, f"Renovada hasta el {new.end_date:%d/%m/%Y}. Se generó el cargo correspondiente.")
    else:
        messages.error(request, "El plan ya no está activo; vendé una membresía nueva.")
    return redirect(f"/socios/{m.member_id}/?tab=membresias")


@require_POST
@perm_required('memberships_cancel')
def membership_cancel(request, pk):
    m = get_object_or_404(Membership, pk=pk)
    m.status = Membership.Status.CANCELLED
    m.auto_renew = False
    m.save(update_fields=["status", "auto_renew"])
    cancelled = 0
    for ch in m.charges.filter(status=Charge.Status.PENDING):
        ch.status = Charge.Status.CANCELLED
        ch.save(update_fields=["status"])
        cancelled += 1
    AuditLog.log(request.user, "membership_cancel", f"Canceló {m}")
    messages.success(request, f"Membresía cancelada ({cancelled} cargos pendientes anulados).")
    return redirect(f"/socios/{m.member_id}/?tab=membresias")


@require_POST
@perm_required('freeze')
def membership_toggle_renew(request, pk):
    m = get_object_or_404(Membership, pk=pk)
    m.auto_renew = not m.auto_renew
    m.save(update_fields=["auto_renew"])
    return redirect(f"/socios/{m.member_id}/?tab=membresias")
