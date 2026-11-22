import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin


class SaasPlan(models.Model):
    """Plan comercial que CoreX le vende a cada gimnasio."""
    code = models.SlugField("código", unique=True)
    name = models.CharField("nombre", max_length=80)
    price_monthly = models.DecimalField("precio mensual", max_digits=12, decimal_places=2, default=0)
    max_members = models.PositiveIntegerField("socios activos máx.", null=True, blank=True, help_text="Vacío = ilimitado")
    max_staff = models.PositiveIntegerField("usuarios de staff máx.", null=True, blank=True, help_text="Vacío = ilimitado")
    features = models.JSONField("funciones", default=dict, blank=True,
                                help_text='Ej: {"crm": true, "mercadopago": true, "arca": true, "push": true}')
    is_active = models.BooleanField("activo", default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "price_monthly")
        verbose_name = "plan SaaS"
        verbose_name_plural = "planes SaaS"

    def __str__(self):
        return self.name

    def has(self, feature):
        return bool(self.features.get(feature, True))


class Gym(TenantMixin):
    class Status(models.TextChoices):
        TRIALING = "trialing", "En prueba"
        ACTIVE = "active", "Activo"
        PAST_DUE = "past_due", "Pago vencido"
        SUSPENDED = "suspended", "Suspendido"
        CANCELED = "canceled", "Cancelado"

    name = models.CharField("nombre", max_length=120)
    slug = models.SlugField(unique=True)
    cuit = models.CharField(max_length=13, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField("teléfono", max_length=40, blank=True)
    plan = models.ForeignKey(SaasPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="gyms")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIALING)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    grace_days = models.PositiveSmallIntegerField(default=7)
    suspended_reason = models.CharField(max_length=200, blank=True)
    hub_ref = models.CharField(max_length=80, unique=True, null=True, blank=True)
    hub_limits = models.JSONField("límites del Hub", default=dict, blank=True,
                                  help_text='Los manda CoreX Hub con el plan. Ej: {"socios_activos": 300, "usuarios_staff": 5}')
    created_at = models.DateTimeField(auto_now_add=True)

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = "gimnasio"
        verbose_name_plural = "gimnasios"

    def __str__(self):
        return self.name

    @property
    def is_public(self):
        return self.schema_name == settings.PUBLIC_SCHEMA_NAME

    @property
    def effective_state(self):
        """Estado real según fechas (igual criterio que GestionAR)."""
        now = timezone.now()
        if self.status == self.Status.TRIALING:
            if self.trial_ends_at and self.trial_ends_at < now:
                return "expired"
            return "trialing"
        if self.status == self.Status.ACTIVE:
            if self.current_period_end and self.current_period_end < now:
                if self.current_period_end + timedelta(days=self.grace_days) < now:
                    return "suspended"
                return "past_due"
            return "active"
        return self.status

    @property
    def is_blocked(self):
        return self.effective_state in ("suspended", "canceled", "expired")

    @property
    def days_left(self):
        end = self.trial_ends_at if self.status == self.Status.TRIALING else self.current_period_end
        if not end:
            return None
        return (end - timezone.now()).days

    def effective_limits(self):
        """Límites vigentes: los del Hub mandan; si no hay, los del plan de EntrenAR."""
        lim = dict(self.hub_limits or {})
        if self.plan:
            if self.plan.max_members and "socios_activos" not in lim:
                lim["socios_activos"] = self.plan.max_members
            if self.plan.max_staff and "usuarios_staff" not in lim:
                lim["usuarios_staff"] = self.plan.max_staff
        return lim

    @property
    def max_members(self):
        v = self.effective_limits().get("socios_activos")
        return int(v) if v else None

    @property
    def max_staff(self):
        v = self.effective_limits().get("usuarios_staff")
        return int(v) if v else None

    def primary_url(self):
        d = self.domains.filter(is_primary=True).first() or self.domains.first()
        if not d:
            return ""
        scheme = "http" if settings.DEBUG else "https"
        port = settings.PUBLIC_PORT_SUFFIX if settings.DEBUG else ""
        return f"{scheme}://{d.domain}{port}"


class Domain(DomainMixin):
    class Meta:
        verbose_name = "dominio"


class HubEvent(models.Model):
    """Cola de envíos hacia CoreX Hub (con reintentos).

    `event` = "metricas" (POST /api/v1/metricas/) o "estado" (POST /api/v1/tenants/estado/).
    """
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event = models.CharField(max_length=60)
    tenant_slug = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_try_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class UsedSSOToken(models.Model):
    jti = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(auto_now_add=True)


# ------------------------------------------------------------------ plug-in de IA (nutrición)

def _default_price():
    from decimal import Decimal
    return Decimal(str(getattr(settings, "AI_PRICE_PER_1K_TOKENS", "8")))


def _default_max_daily():
    return int(getattr(settings, "AI_DEFAULT_MAX_DAILY", 10))


class AIAddon(models.Model):
    """Plug-in «Análisis de comidas con IA» de un gimnasio.

    CoreX lo habilita, fija el tope diario por alumno y el precio. El gimnasio lo activa, elige su límite
    diario (dentro del tope) y, si quiere, un tope de gasto mensual. CoreX le factura los tokens a fin de mes.
    """

    gym = models.OneToOneField(Gym, on_delete=models.CASCADE, related_name="ai_addon", verbose_name="gimnasio")
    # --- lo define CoreX
    allowed = models.BooleanField("habilitado por CoreX", default=False)
    max_daily_limit = models.PositiveSmallIntegerField("tope diario por alumno (CoreX)", default=_default_max_daily)
    price_per_1k_tokens = models.DecimalField("precio por 1.000 tokens (ARS)", max_digits=10, decimal_places=4,
                                              default=_default_price)
    # --- lo define el gimnasio
    active = models.BooleanField("activado por el gimnasio", default=False)
    daily_limit = models.PositiveSmallIntegerField("análisis por alumno por día", default=3)
    monthly_cap = models.DecimalField("tope de gasto mensual (ARS)", max_digits=12, decimal_places=2, null=True,
                                      blank=True, help_text="Vacío = sin tope. Al llegar, la IA se pausa hasta el mes que viene.")
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "plug-in de IA"
        verbose_name_plural = "plug-ins de IA"

    def __str__(self):
        return f"IA · {self.gym}"

    @property
    def enabled(self):
        return self.allowed and self.active

    @property
    def effective_daily_limit(self):
        return min(self.daily_limit, self.max_daily_limit)

    def cost_for(self, tokens):
        from decimal import ROUND_HALF_UP, Decimal
        return (Decimal(tokens) / 1000 * self.price_per_1k_tokens).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @classmethod
    def for_gym(cls, gym):
        if gym is None or not getattr(gym, "pk", None):
            return None
        obj, _ = cls.objects.get_or_create(gym_id=gym.pk)
        return obj


class AIUsageMonth(models.Model):
    """Tokens consumidos por un gimnasio en un mes (se suma en cada análisis; se cierra para facturar)."""

    class Status(models.TextChoices):
        OPEN = "open", "En curso"
        CLOSED = "closed", "Cerrado"
        SENT = "sent", "Enviado a facturar"

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="ai_usage", verbose_name="gimnasio")
    month = models.DateField("mes", help_text="Primer día del mes")
    requests = models.PositiveIntegerField("análisis", default=0)
    tokens_in = models.BigIntegerField("tokens de entrada", default=0)
    tokens_out = models.BigIntegerField("tokens de salida", default=0)
    status = models.CharField("estado", max_length=8, choices=Status.choices, default=Status.OPEN)
    price_per_1k_tokens = models.DecimalField("precio aplicado por 1.000 tokens", max_digits=10, decimal_places=4,
                                              null=True, blank=True)
    amount = models.DecimalField("importe a facturar (ARS)", max_digits=12, decimal_places=2, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    hub_event = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ("-month", "gym__name")
        constraints = [models.UniqueConstraint(fields=["gym", "month"], name="aiusage_gym_month")]
        verbose_name = "consumo de IA del mes"
        verbose_name_plural = "consumo de IA por mes"

    def __str__(self):
        return f"{self.gym} · {self.month:%m/%Y}"

    @property
    def tokens(self):
        return self.tokens_in + self.tokens_out


class InfraCost(models.Model):
    """Costos fijos de CoreX para operar EntrenAR (servidor, base, email, dominios…). Se ven en Costos."""

    class Category(models.TextChoices):
        SERVER = "server", "Servidor / hosting"
        DATABASE = "database", "Base de datos / backups"
        EMAIL = "email", "Email / notificaciones"
        DOMAIN = "domain", "Dominios / SSL"
        AI = "ai", "IA (fijo)"
        OTHER = "other", "Otros"

    class Currency(models.TextChoices):
        ARS = "ARS", "Pesos"
        USD = "USD", "Dólares"

    name = models.CharField("concepto", max_length=120)
    category = models.CharField("categoría", max_length=10, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField("importe mensual", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, choices=Currency.choices, default=Currency.ARS)
    shared = models.BooleanField("compartido con otros SaaS", default=False,
                                 help_text="Si el VPS lo usan varios sistemas, indicá qué parte le toca a EntrenAR")
    share_pct = models.PositiveSmallIntegerField("% que corresponde a EntrenAR", default=100)
    since = models.DateField("desde", default=timezone.localdate)
    until = models.DateField("hasta", null=True, blank=True)
    notes = models.CharField("notas", max_length=200, blank=True)

    class Meta:
        ordering = ("category", "name")
        verbose_name = "costo fijo"
        verbose_name_plural = "costos fijos"

    def __str__(self):
        return self.name

    def monthly_ars(self):
        from decimal import Decimal
        amount = self.amount * (Decimal(str(settings.AI_FX_ARS)) if self.currency == "USD" else 1)
        return (amount * Decimal(self.share_pct) / 100).quantize(Decimal("0.01"))

    def applies_to(self, month):
        """month = primer día del mes."""
        from datetime import date
        end = date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)
        return self.since < end and (self.until is None or self.until >= month)
