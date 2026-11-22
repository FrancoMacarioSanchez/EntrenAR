"""Tareas diarias de cada gimnasio (correr con: python manage.py gym_daily)."""
from datetime import timedelta

from django.utils import timezone

from .models import GymSettings, Notification
from .notify import notify


def daily_job():
    from apps.billing.services import apply_late_fees
    from apps.classes.models import ClassBooking
    from apps.crm.services import generate_retention_tasks, segment_members
    from apps.memberships.models import Membership
    from apps.memberships.services import renew

    cfg = GymSettings.get()
    today = timezone.localdate()
    out = {}

    # 1) descongelar membresías cuyo congelamiento terminó
    unfrozen = 0
    for m in Membership.objects.filter(status=Membership.Status.FROZEN):
        if not m.freezes.filter(start_date__lte=today, end_date__gte=today).exists():
            m.status = Membership.Status.ACTIVE
            m.save(update_fields=["status"])
            unfrozen += 1
    out["unfrozen"] = unfrozen

    # 2) congelar las que arrancan congelamiento hoy
    Membership.objects.filter(freezes__start_date=today, status=Membership.Status.ACTIVE).update(
        status=Membership.Status.FROZEN)

    # 3) marcar vencidas
    out["expired"] = Membership.objects.filter(status=Membership.Status.ACTIVE, end_date__lt=today).update(
        status=Membership.Status.EXPIRED)

    # 4) renovaciones automáticas (vencen hoy o mañana)
    renewed = 0
    for m in Membership.objects.filter(auto_renew=True, renewed_to__isnull=True, end_date__lte=today + timedelta(days=1),
                                       end_date__gte=today - timedelta(days=1), member__status="active"
                                       ).exclude(status=Membership.Status.CANCELLED).select_related("member", "plan"):
        if m.plan.period == "day":
            continue
        new = renew(m)
        if new:
            renewed += 1
            if m.member.user:
                notify(m.member.user, "Renovamos tu membresía",
                       f"{new.plan.name} hasta el {new.end_date:%d/%m/%Y}. Podés pagarla desde la app.",
                       "/app/membresia", kind="membership")
    out["renewed"] = renewed

    # 5) avisos de vencimiento
    notice_day = today + timedelta(days=cfg.expiry_notice_days)
    sent = 0
    for m in Membership.objects.filter(end_date=notice_day, renewed_to__isnull=True, auto_renew=False).exclude(
            status=Membership.Status.CANCELLED).select_related("member__user"):
        if m.member.user:
            notify(m.member.user, "Tu membresía está por vencer",
                   f"Vence el {m.end_date:%d/%m}. ¡Renovala para seguir entrenando!", "/app/membresia",
                   kind="membership", email=True)
            sent += 1
    out["expiry_notices"] = sent

    # 6) recargos por mora
    out["late_fees"] = apply_late_fees()

    # 7) clases de ayer sin asistencia -> ausente
    out["no_show"] = ClassBooking.objects.filter(date__lt=today, status=ClassBooking.Status.BOOKED).update(
        status=ClassBooking.Status.NO_SHOW)

    # 8) CRM: tareas automáticas de retención
    out["tasks"] = generate_retention_tasks()

    # 9) cumpleaños
    for member in segment_members("birthday").select_related("user"):
        if member.user and not Notification.objects.filter(user=member.user, kind="birthday",
                                                           created_at__date=today).exists():
            notify(member.user, f"¡Feliz cumpleaños, {member.first_name}! 🎂",
                   f"Todo el equipo de {cfg.display_name} te desea un gran día.", "/app/", kind="birthday")

    # 10) limpieza de notificaciones viejas
    Notification.objects.filter(is_read=True, created_at__lt=timezone.now() - timedelta(days=90)).delete()
    return out
