"""Recepción: control de acceso por QR / DNI / búsqueda."""
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.members.models import Member
from apps.memberships.models import CheckIn
from apps.memberships.services import check_in, evaluate_access, find_member

from .permissions import perm_required


@perm_required('checkin')
def checkin_screen(request):
    today = timezone.localdate()
    recent = CheckIn.objects.select_related("member").filter(created_at__date=today)[:25]
    return render(request, "panel/frontdesk/checkin.html", {
        "recent": recent, "count_today": CheckIn.objects.filter(created_at__date=today, allowed=True).count(),
        "section": "recepcion"})


@require_POST
@perm_required('checkin')
def checkin_submit(request):
    """Recibe el código del QR / DNI (lector USB o cámara) y registra el ingreso."""
    code = request.POST.get("code", "").strip()
    member = None
    if request.POST.get("member_id"):
        member = Member.objects.filter(pk=request.POST["member_id"]).first()
    else:
        member = find_member(code)
    if not member:
        matches = []
        if len(code) >= 3:
            matches = Member.objects.filter(Q(first_name__icontains=code) | Q(last_name__icontains=code)
                                            | Q(dni__icontains=code))[:8]
        return render(request, "panel/frontdesk/_result.html", {"not_found": True, "code": code, "matches": matches})
    force = request.POST.get("force") == "1" and request.user.is_staff_member
    method = "qr" if code and code.upper() == member.access_code else ("dni" if code else "manual")
    c, allowed, reason, membership = check_in(member, method=method, user=request.user, force=force)
    return render(request, "panel/frontdesk/_result.html", {
        "member": member, "allowed": allowed, "reason": reason, "membership": membership, "checkin": c,
        "debt": member.debt, "visits_left": membership.visits_left() if membership else None})


@perm_required('checkin')
def checkin_preview(request, pk):
    member = get_object_or_404(Member, pk=pk)
    allowed, reason, membership = evaluate_access(member)
    return render(request, "panel/frontdesk/_result.html", {
        "member": member, "allowed": allowed, "reason": reason, "membership": membership, "preview": True,
        "debt": member.debt})


@perm_required('checkin')
def recent_checkins(request):
    today = timezone.localdate()
    recent = CheckIn.objects.select_related("member").filter(created_at__date=today)[:25]
    return render(request, "panel/frontdesk/_recent.html", {"recent": recent})


# ------------------------------------------------------------------ QR de autoingreso
def _checkin_url(request, k):
    return request.build_absolute_uri(f"/app/ingreso?k={k}")


@perm_required('checkin')
def qr_poster(request):
    """Cartel imprimible con el QR fijo del gimnasio."""
    from apps.core.models import GymSettings
    from apps.core.utils import new_checkin_key

    cfg = GymSettings.get()
    if request.method == "POST" and request.user.can("settings"):
        cfg.checkin_key = new_checkin_key()
        cfg.save(update_fields=["checkin_key"])
        messages.success(request, "Generamos un QR nuevo. El anterior dejó de funcionar: imprimí el cartel otra vez.")
        return redirect("panel:qr_poster")
    from apps.core.selfcheckin import static_code

    return render(request, "panel/frontdesk/qr_poster.html", {
        "url": _checkin_url(request, cfg.checkin_key), "cfg": cfg, "section": "recepcion",
        "code": static_code(cfg.checkin_key)})


@perm_required('checkin')
def qr_screen(request):
    """Pantalla para tablet/TV en la entrada: QR que cambia cada 30 segundos."""
    return render(request, "panel/frontdesk/qr_screen.html")


@perm_required('checkin')
def qr_screen_token(request):
    from apps.core.models import GymSettings
    from apps.core.selfcheckin import WINDOW, rotating_pin, rotating_token

    cfg = GymSettings.get()
    today = timezone.localdate()
    last = [{"name": c.member.full_name, "first": c.member.first_name, "initials": c.member.initials,
             "photo": c.member.photo.url if c.member.photo else None, "allowed": c.allowed,
             "at": timezone.localtime(c.created_at).strftime("%H:%M"), "reason": c.reason}
            for c in CheckIn.objects.select_related("member").filter(created_at__date=today)[:6]]
    return JsonResponse({"url": _checkin_url(request, rotating_token(cfg.checkin_key)), "window": WINDOW,
                         "pin": rotating_pin(cfg.checkin_key),
                         "enabled": cfg.self_checkin_enabled, "last": last,
                         "count": CheckIn.objects.filter(created_at__date=today, allowed=True).count()})
