"""Segmentos, retención, conversión de leads y campañas."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.core.models import GymSettings
from apps.members.models import Member

from .models import Lead, LeadActivity, Task


def active_members():
    today = timezone.localdate()
    return Member.objects.filter(status=Member.Status.ACTIVE, memberships__start_date__lte=today,
                                 memberships__end_date__gte=today).exclude(memberships__status="cancelled").distinct()


def segment_members(segment):
    cfg = GymSettings.get()
    today = timezone.localdate()
    if segment == "active":
        return active_members()
    if segment == "expiring":
        return Member.objects.filter(
            memberships__end_date__gte=today, memberships__end_date__lte=today + timedelta(days=cfg.expiry_notice_days),
            memberships__renewed_to__isnull=True).exclude(memberships__status="cancelled").distinct()
    if segment == "expired":
        recent = Member.objects.annotate(last_end=Max("memberships__end_date")).filter(
            last_end__lt=today, last_end__gte=today - timedelta(days=60))
        return recent.exclude(status=Member.Status.SUSPENDED)
    if segment == "inactive":
        limit = timezone.now() - timedelta(days=cfg.inactivity_alert_days)
        return active_members().annotate(last=Max("checkins__created_at", filter=Q(checkins__allowed=True))).filter(
            Q(last__lt=limit) | Q(last__isnull=True))
    if segment == "debt":
        return Member.objects.filter(charges__status__in=["pending", "partial"],
                                     charges__due_date__lt=today).distinct()
    if segment == "birthday":
        return Member.objects.filter(birth_date__month=today.month, birth_date__day=today.day,
                                     status=Member.Status.ACTIVE)
    return Member.objects.none()


def retention_overview():
    return {
        "expiring": segment_members("expiring"),
        "expired": segment_members("expired"),
        "inactive": segment_members("inactive"),
        "debt": segment_members("debt"),
        "birthday": segment_members("birthday"),
    }


@transaction.atomic
def convert_lead(lead, user=None, **member_fields):
    first, _, last = lead.name.partition(" ")
    data = {"first_name": first, "last_name": last or "-", "phone": lead.phone, "email": lead.email,
            "source": lead.get_source_display()}
    data.update({k: v for k, v in member_fields.items() if v not in (None, "")})
    member = Member.objects.create(**data)
    lead.converted_member = member
    lead.stage = Lead.Stage.WON
    lead.save(update_fields=["converted_member", "stage"])
    LeadActivity.objects.create(lead=lead, kind=LeadActivity.Kind.STAGE, text="Convertido en socio", by=user)
    return member


def move_lead(lead, stage, user=None, position=None):
    if lead.stage != stage:
        LeadActivity.objects.create(lead=lead, kind=LeadActivity.Kind.STAGE, by=user,
                                    text=f"{lead.get_stage_display()} → {Lead.Stage(stage).label}")
        lead.stage = stage
    if position is not None:
        lead.position = position
    lead.save(update_fields=["stage", "position"])


def generate_retention_tasks():
    """Crea tareas automáticas para recepción (sin duplicar)."""
    today = timezone.localdate()
    created = 0
    for m in segment_members("inactive")[:200]:
        key = f"inactive:{m.pk}:{today:%Y-%W}"
        if not Task.objects.filter(auto_key=key).exists():
            Task.objects.create(title=f"Contactar a {m.full_name}: hace días que no viene", member=m, auto_key=key,
                                priority=Task.Priority.NORMAL, assigned_to=m.trainer)
            created += 1
    for m in segment_members("expired")[:200]:
        key = f"expired:{m.pk}:{today:%Y-%m}"
        if not Task.objects.filter(auto_key=key).exists():
            Task.objects.create(title=f"Recuperar a {m.full_name}: membresía vencida", member=m, auto_key=key,
                                priority=Task.Priority.HIGH)
            created += 1
    for lead in Lead.objects.filter(next_contact=today).exclude(stage__in=["won", "lost"]):
        key = f"lead:{lead.pk}:{today}"
        if not Task.objects.filter(auto_key=key).exists():
            Task.objects.create(title=f"Seguimiento lead: {lead.name}", lead=lead, auto_key=key,
                                assigned_to=lead.assigned_to)
            created += 1
    return created


def run_campaign(campaign, user=None):
    """Push/email: envía. WhatsApp: devuelve los links wa.me para enviar uno por uno."""
    from django.conf import settings
    from django.core.mail import send_mail

    from apps.core.notify import notify
    from apps.core.utils import wa_link

    tpl = campaign.template
    rows, sent = [], 0
    if campaign.segment == "leads":
        targets = [(None, lead) for lead in Lead.objects.exclude(stage__in=["won", "lost"])]
    else:
        targets = [(m, None) for m in segment_members(campaign.segment)]
    for member, lead in targets:
        text = tpl.render(member=member, lead=lead)
        name = member.full_name if member else lead.name
        phone = member.phone if member else lead.phone
        email = member.email if member else lead.email
        if tpl.channel == "whatsapp":
            link = wa_link(phone, text)
            if link:
                rows.append({"name": name, "link": link, "text": text})
        elif tpl.channel == "email" and email:
            send_mail(tpl.subject or campaign.name, text, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)
            sent += 1
        elif tpl.channel == "push" and member and member.user:
            notify(member.user, tpl.subject or campaign.name, text, "/app/", kind="campaign")
            sent += 1
    campaign.sent_at = timezone.now()
    campaign.sent_count = sent or len(rows)
    campaign.save(update_fields=["sent_at", "sent_count"])
    return rows, sent
