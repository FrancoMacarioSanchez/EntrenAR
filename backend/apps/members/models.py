import uuid
from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.utils import TenantPath


def access_code():
    return uuid.uuid4().hex[:12].upper()


class Member(models.Model):
    class Sex(models.TextChoices):
        MALE = "M", "Masculino"
        FEMALE = "F", "Femenino"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        SUSPENDED = "suspended", "Suspendido"

    class Goal(models.TextChoices):
        HYPERTROPHY = "hypertrophy", "Hipertrofia"
        STRENGTH = "strength", "Fuerza"
        FAT_LOSS = "fat_loss", "Descenso de grasa"
        HEALTH = "health", "Salud general"
        PERFORMANCE = "performance", "Rendimiento deportivo"
        REHAB = "rehab", "Rehabilitación"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="member")
    first_name = models.CharField("nombre", max_length=80)
    last_name = models.CharField("apellido", max_length=80)
    dni = models.CharField("DNI", max_length=12, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField("teléfono / WhatsApp", max_length=40, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    sex = models.CharField("sexo biológico", max_length=1, choices=Sex.choices, default=Sex.MALE,
                           help_text="Se usa para las fórmulas de composición corporal.")
    height_cm = models.DecimalField("altura (cm)", max_digits=5, decimal_places=1, null=True, blank=True)
    address = models.CharField("dirección", max_length=200, blank=True)
    photo = models.ImageField("foto", upload_to=TenantPath("members"), null=True, blank=True)
    goal = models.CharField("objetivo", max_length=20, choices=Goal.choices, default=Goal.HEALTH)
    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="students", limit_choices_to={"role": "trainer"},
                                verbose_name="entrenador asignado")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    emergency_name = models.CharField("contacto de emergencia", max_length=120, blank=True)
    emergency_phone = models.CharField("teléfono de emergencia", max_length=40, blank=True)
    medical_notes = models.TextField("observaciones médicas / lesiones", blank=True)
    medical_clearance_until = models.DateField("apto físico vence", null=True, blank=True)
    medical_clearance_file = models.FileField("apto físico (archivo)", upload_to=TenantPath("aptos"), null=True,
                                              blank=True)
    joined_at = models.DateField("fecha de alta", default=date.today)
    source = models.CharField("cómo nos conoció", max_length=60, blank=True)
    notes = models.TextField("notas internas", blank=True)
    avatar = models.JSONField("avatar 3D", default=dict, blank=True)
    access_code = models.CharField("código de acceso (QR)", max_length=12, unique=True, default=access_code)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name")
        verbose_name = "socio"
        verbose_name_plural = "socios"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self):
        return (self.first_name[:1] + self.last_name[:1]).upper()

    @property
    def age(self):
        if not self.birth_date:
            return None
        t = date.today()
        return t.year - self.birth_date.year - ((t.month, t.day) < (self.birth_date.month, self.birth_date.day))

    @property
    def current_membership(self):
        today = timezone.localdate()
        return (self.memberships.filter(start_date__lte=today, end_date__gte=today)
                .exclude(status="cancelled").order_by("-end_date").first())

    @property
    def last_membership(self):
        return self.memberships.exclude(status="cancelled").order_by("-end_date").first()

    @property
    def debt(self):
        from apps.billing.models import Charge

        return sum((c.balance for c in Charge.objects.filter(member=self, status__in=["pending", "partial"])), 0)

    @property
    def last_checkin(self):
        c = self.checkins.filter(allowed=True).order_by("-created_at").first()
        return c.created_at if c else None

    @property
    def medical_ok(self):
        return bool(self.medical_clearance_until and self.medical_clearance_until >= timezone.localdate())

    @property
    def days_since_last_visit(self):
        last = self.last_checkin
        return (timezone.now() - last).days if last else None

    def membership_state(self):
        """('active'|'expiring'|'grace'|'expired'|'frozen'|'none', membresía)"""
        from apps.core.models import GymSettings

        today = timezone.localdate()
        m = self.last_membership
        if not m:
            return "none", None
        if m.status == "frozen":
            return "frozen", m
        if m.start_date <= today <= m.end_date:
            notice = GymSettings.get().expiry_notice_days
            return ("expiring" if (m.end_date - today).days <= notice else "active"), m
        if m.end_date < today:
            grace = GymSettings.get().access_grace_days
            return ("grace" if today <= m.end_date + timedelta(days=grace) else "expired"), m
        return "active", m  # empieza en el futuro


class MemberNote(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="member_notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = models.TextField("nota")
    visible_to_member = models.BooleanField("visible para el alumno", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
