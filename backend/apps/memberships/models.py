from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.members.models import Member


class Plan(models.Model):
    class Period(models.TextChoices):
        DAY = "day", "Diario"
        WEEK = "week", "Semanal"
        MONTH = "month", "Mensual"
        QUARTER = "quarter", "Trimestral"
        SEMESTER = "semester", "Semestral"
        YEAR = "year", "Anual"

    class Access(models.TextChoices):
        UNLIMITED = "unlimited", "Pase libre"
        WEEKLY = "weekly", "X veces por semana"
        TOTAL = "total", "X ingresos en el período"

    DAYS = {"day": 1, "week": 7, "month": 30, "quarter": 90, "semester": 180, "year": 365}

    name = models.CharField("nombre", max_length=100)
    description = models.TextField("descripción", blank=True)
    period = models.CharField("período", max_length=10, choices=Period.choices, default=Period.MONTH)
    duration_count = models.PositiveSmallIntegerField("cantidad de períodos", default=1)
    price = models.DecimalField("precio", max_digits=12, decimal_places=2)
    access_type = models.CharField("tipo de acceso", max_length=10, choices=Access.choices, default=Access.UNLIMITED)
    visits_limit = models.PositiveSmallIntegerField("límite de ingresos", null=True, blank=True)
    includes_classes = models.BooleanField("incluye clases grupales", default=True)
    includes_routine = models.BooleanField("incluye rutina personalizada", default=True)
    color = models.CharField(max_length=9, default="#ff5a1f")
    is_active = models.BooleanField("activo", default=True)
    order = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        ordering = ("order", "price")
        verbose_name = "plan"
        verbose_name_plural = "planes"

    def __str__(self):
        return self.name

    @property
    def duration_days(self):
        return self.DAYS.get(self.period, 30) * self.duration_count

    def end_date_from(self, start):
        if self.period in ("month", "quarter", "semester", "year"):
            months = {"month": 1, "quarter": 3, "semester": 6, "year": 12}[self.period] * self.duration_count
            y, m = divmod(start.month - 1 + months, 12)
            year, month = start.year + y, m + 1
            import calendar

            day = min(start.day, calendar.monthrange(year, month)[1])
            return start.replace(year=year, month=month, day=day) - timedelta(days=1)
        return start + timedelta(days=self.duration_days - 1)


class Promotion(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Descuento %"
        AMOUNT = "amount", "Descuento en pesos"
        EXTRA_DAYS = "extra_days", "Días extra de regalo"
        FREE_ENROLLMENT = "free_enrollment", "Matrícula bonificada"

    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=250, blank=True)
    kind = models.CharField("tipo", max_length=16, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField("valor", max_digits=12, decimal_places=2, default=0,
                                help_text="% de descuento, monto en pesos o cantidad de días según el tipo.")
    plans = models.ManyToManyField(Plan, blank=True, related_name="promotions", verbose_name="planes",
                                   help_text="Vacío = vale para todos los planes.")
    starts_on = models.DateField("desde", default=timezone.localdate)
    ends_on = models.DateField("hasta", null=True, blank=True)
    code = models.CharField("código (opcional)", max_length=30, blank=True,
                            help_text="Si lo completás, la promo solo se aplica cuando el socio dice el código.")
    only_new_members = models.BooleanField("solo socios nuevos", default=False)
    max_uses = models.PositiveIntegerField("usos máximos", null=True, blank=True)
    uses = models.PositiveIntegerField("usos", default=0, editable=False)
    show_in_app = models.BooleanField("mostrar en la app de los alumnos", default=True)
    color = models.CharField(max_length=9, default="#ff5a1f")
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_active", "-starts_on")
        verbose_name = "promoción"
        verbose_name_plural = "promociones"

    def __str__(self):
        return self.name

    @property
    def summary(self):
        v = f"{self.value:g}"
        return {"percent": f"{v}% off", "amount": f"$ {v} off", "extra_days": f"+{v} días",
                "free_enrollment": "Matrícula gratis"}[self.kind]

    def is_current(self, day=None):
        day = day or timezone.localdate()
        return (self.is_active and self.starts_on <= day and (not self.ends_on or day <= self.ends_on)
                and (self.max_uses is None or self.uses < self.max_uses))

    def problem_for(self, plan, member):
        """None si se puede aplicar, o el motivo por el que no."""
        if not self.is_current():
            return "La promoción no está vigente."
        if self.pk and self.plans.exists() and not self.plans.filter(pk=plan.pk).exists():
            return f"La promoción no aplica al plan {plan.name}."
        if self.only_new_members and member.memberships.exclude(status="cancelled").exists():
            return "La promoción es solo para socios nuevos."
        return None


class Membership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        FROZEN = "frozen", "Congelada"
        EXPIRED = "expired", "Vencida"
        CANCELLED = "cancelled", "Cancelada"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="memberships", verbose_name="socio")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="memberships")
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta")
    price = models.DecimalField("precio", max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField("descuento (%)", max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField("descuento ($)", max_digits=12, decimal_places=2, default=0)
    promotion = models.ForeignKey(Promotion, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="memberships", verbose_name="promoción")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    auto_renew = models.BooleanField("renovación automática", default=True)
    renewed_to = models.OneToOneField("self", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="renewed_from")
    notes = models.CharField("notas", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "membresía"
        verbose_name_plural = "membresías"

    def __str__(self):
        return f"{self.member} · {self.plan} ({self.start_date:%d/%m} → {self.end_date:%d/%m/%Y})"

    @property
    def final_price(self):
        from decimal import Decimal

        from apps.core.utils import money

        price = Decimal(str(self.price))
        discount = Decimal(str(self.discount_percent or 0))
        amount = Decimal(str(self.discount_amount or 0))
        return money(max(price * (Decimal("1") - discount / Decimal("100")) - amount, Decimal("0")))

    @property
    def remaining_days(self):
        return (self.end_date - timezone.localdate()).days

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.start_date <= today <= self.end_date

    def visits_in_range(self, start, end):
        return self.checkins.filter(allowed=True, created_at__date__gte=start, created_at__date__lte=end).count()

    def visits_left(self):
        """None = ilimitado."""
        plan = self.plan
        if plan.access_type == Plan.Access.UNLIMITED or not plan.visits_limit:
            return None
        today = timezone.localdate()
        if plan.access_type == Plan.Access.WEEKLY:
            week_start = today - timedelta(days=today.weekday())
            used = self.visits_in_range(week_start, today)
        else:
            used = self.visits_in_range(self.start_date, self.end_date)
        return max(plan.visits_limit - used, 0)


class Freeze(models.Model):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="freezes")
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta")
    reason = models.CharField("motivo", max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1


class CheckIn(models.Model):
    class Method(models.TextChoices):
        QR = "qr", "QR"
        DNI = "dni", "DNI"
        MANUAL = "manual", "Manual"
        APP = "app", "App"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="checkins")
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="checkins")
    method = models.CharField(max_length=8, choices=Method.choices, default=Method.MANUAL)
    allowed = models.BooleanField(default=True)
    reason = models.CharField(max_length=200, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "ingreso"
        verbose_name_plural = "ingresos"
