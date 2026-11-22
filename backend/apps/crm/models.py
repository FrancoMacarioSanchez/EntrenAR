from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.members.models import Member
from apps.memberships.models import Plan


class Lead(models.Model):
    class Stage(models.TextChoices):
        NEW = "new", "Nuevo"
        CONTACTED = "contacted", "Contactado"
        TRIAL = "trial", "Clase de prueba"
        NEGOTIATION = "negotiation", "Negociando"
        WON = "won", "Ganado"
        LOST = "lost", "Perdido"

    class Source(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        WHATSAPP = "whatsapp", "WhatsApp"
        WALK_IN = "walk_in", "Se acercó al gimnasio"
        REFERRAL = "referral", "Recomendación"
        WEB = "web", "Web"
        GOOGLE = "google", "Google"
        OTHER = "other", "Otro"

    name = models.CharField("nombre", max_length=120)
    phone = models.CharField("teléfono", max_length=40, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField("origen", max_length=12, choices=Source.choices, default=Source.INSTAGRAM)
    stage = models.CharField("etapa", max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    interest = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="plan de interés")
    goal = models.CharField("objetivo", max_length=120, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="leads", verbose_name="responsable")
    trial_date = models.DateTimeField("fecha de clase de prueba", null=True, blank=True)
    next_contact = models.DateField("próximo contacto", null=True, blank=True)
    value = models.DecimalField("valor estimado", max_digits=12, decimal_places=2, null=True, blank=True)
    lost_reason = models.CharField("motivo de pérdida", max_length=160, blank=True)
    notes = models.TextField("notas", blank=True)
    referred_by = models.ForeignKey(Member, null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals",
                                    verbose_name="referido por")
    converted_member = models.OneToOneField(Member, null=True, blank=True, on_delete=models.SET_NULL,
                                            related_name="lead")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "-created_at")
        verbose_name = "lead"
        verbose_name_plural = "leads"

    def __str__(self):
        return self.name

    @property
    def is_overdue(self):
        return bool(self.next_contact and self.next_contact < timezone.localdate()
                    and self.stage not in (self.Stage.WON, self.Stage.LOST))


class LeadActivity(models.Model):
    class Kind(models.TextChoices):
        CALL = "call", "Llamada"
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "Email"
        VISIT = "visit", "Visita"
        NOTE = "note", "Nota"
        STAGE = "stage", "Cambio de etapa"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTE)
    text = models.CharField("detalle", max_length=500)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "low", "Baja"
        NORMAL = "normal", "Normal"
        HIGH = "high", "Alta"

    title = models.CharField("tarea", max_length=200)
    due_date = models.DateField("vence", default=timezone.localdate)
    priority = models.CharField("prioridad", max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="tasks", verbose_name="responsable")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    member = models.ForeignKey(Member, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks",
                               verbose_name="socio")
    done = models.BooleanField("hecha", default=False)
    auto_key = models.CharField(max_length=80, blank=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("done", "due_date", "-priority")
        verbose_name = "tarea"
        verbose_name_plural = "tareas"

    def __str__(self):
        return self.title


class MessageTemplate(models.Model):
    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "Email"
        PUSH = "push", "Notificación app"

    name = models.CharField("nombre", max_length=80)
    channel = models.CharField("canal", max_length=10, choices=Channel.choices, default=Channel.WHATSAPP)
    subject = models.CharField("asunto (email/push)", max_length=120, blank=True)
    body = models.TextField("mensaje", help_text="Variables: {nombre} {apellido} {plan} {vencimiento} {deuda} {gimnasio}")

    class Meta:
        verbose_name = "plantilla de mensaje"
        verbose_name_plural = "plantillas de mensajes"

    def __str__(self):
        return self.name

    def render(self, member=None, lead=None):
        from apps.core.models import GymSettings
        from apps.core.utils import fmt_money

        ctx = {"gimnasio": GymSettings.get().display_name, "nombre": "", "apellido": "", "plan": "",
               "vencimiento": "", "deuda": ""}
        if member:
            m = member.last_membership
            ctx.update(nombre=member.first_name, apellido=member.last_name,
                       plan=m.plan.name if m else "", vencimiento=f"{m.end_date:%d/%m/%Y}" if m else "",
                       deuda=fmt_money(member.debt))
        elif lead:
            ctx.update(nombre=lead.name.split(" ")[0], plan=lead.interest.name if lead.interest else "")
        out = self.body
        for k, v in ctx.items():
            out = out.replace("{" + k + "}", str(v))
        return out


class Campaign(models.Model):
    """Envío masivo a un segmento (push/email; WhatsApp genera la lista de links)."""

    class Segment(models.TextChoices):
        ALL_ACTIVE = "active", "Socios activos"
        EXPIRING = "expiring", "Vencen en los próximos días"
        EXPIRED = "expired", "Vencidos (últimos 60 días)"
        INACTIVE = "inactive", "Activos que no vienen"
        DEBT = "debt", "Con deuda"
        BIRTHDAY = "birthday", "Cumplen años hoy"
        LEADS = "leads", "Leads abiertos"

    name = models.CharField("nombre", max_length=100)
    segment = models.CharField("segmento", max_length=10, choices=Segment.choices)
    template = models.ForeignKey(MessageTemplate, on_delete=models.PROTECT, verbose_name="plantilla")
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "campaña"
        verbose_name_plural = "campañas"

    def __str__(self):
        return self.name
