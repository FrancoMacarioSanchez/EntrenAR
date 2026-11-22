from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from apps.members.models import Member
from apps.memberships.models import Membership


class PaymentMethod(models.Model):
    class Kind(models.TextChoices):
        CASH = "cash", "Efectivo"
        TRANSFER = "transfer", "Transferencia"
        CARD = "card", "Tarjeta"
        MERCADOPAGO = "mercadopago", "Mercado Pago"
        OTHER = "other", "Otro"

    name = models.CharField("nombre", max_length=60, unique=True)
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, default=Kind.OTHER)
    is_invoiceable = models.BooleanField("se factura", default=True)
    surcharge_percent = models.DecimalField("recargo (%)", max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField("activo", default=True)
    order = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "medio de pago"
        verbose_name_plural = "medios de pago"

    def __str__(self):
        return self.name


class Charge(models.Model):
    """Cargo / deuda del socio (cuota, matrícula, producto, recargo...)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PARTIAL = "partial", "Pago parcial"
        PAID = "paid", "Pagado"
        CANCELLED = "cancelled", "Anulado"

    class Kind(models.TextChoices):
        MEMBERSHIP = "membership", "Cuota"
        ENROLLMENT = "enrollment", "Matrícula"
        LATE_FEE = "late_fee", "Recargo por mora"
        PRODUCT = "product", "Producto / servicio"
        OTHER = "other", "Otro"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="charges", verbose_name="socio")
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="charges")
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices, default=Kind.MEMBERSHIP)
    concept = models.CharField("concepto", max_length=160)
    amount = models.DecimalField("importe", max_digits=12, decimal_places=2)
    due_date = models.DateField("vencimiento", default=timezone.localdate)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    late_fee_applied = models.BooleanField(default=False)
    mp_preference_id = models.CharField(max_length=120, blank=True)
    mp_init_point = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-due_date", "-id")
        verbose_name = "cargo"
        verbose_name_plural = "cargos"

    def __str__(self):
        return f"{self.concept} — {self.member}"

    @property
    def paid_amount(self):
        return self.payments.filter(is_void=False).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    @property
    def balance(self):
        if self.status == self.Status.CANCELLED:
            return Decimal("0")
        return max(self.amount - self.paid_amount, Decimal("0"))

    def refresh_status(self, save=True):
        if self.status == self.Status.CANCELLED:
            return
        paid = self.paid_amount
        self.status = (self.Status.PAID if paid >= self.amount else
                       self.Status.PARTIAL if paid > 0 else self.Status.PENDING)
        if save:
            self.save(update_fields=["status"])


class CashSession(models.Model):
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    opened_at = models.DateTimeField(default=timezone.now)
    opening_amount = models.DecimalField("efectivo inicial", max_digits=12, decimal_places=2, default=0)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_amount = models.DecimalField("efectivo contado", max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.CharField("notas", max_length=200, blank=True)

    class Meta:
        ordering = ("-opened_at",)
        verbose_name = "caja"
        verbose_name_plural = "cajas"

    @classmethod
    def current(cls):
        return cls.objects.filter(closed_at__isnull=True).first()

    def totals(self):
        pays = self.payments.filter(is_void=False)
        by_method = list(pays.values("method__name", "method__kind").annotate(total=Sum("amount")).order_by("-total"))
        cash_in = pays.filter(method__kind="cash").aggregate(s=Sum("amount"))["s"] or Decimal("0")
        cash_out = self.expenses.filter(method__kind="cash").aggregate(s=Sum("amount"))["s"] or Decimal("0")
        income = pays.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        expenses = self.expenses.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        expected_cash = self.opening_amount + cash_in - cash_out
        diff = (self.closing_amount - expected_cash) if self.closing_amount is not None else None
        return {"by_method": by_method, "income": income, "expenses": expenses, "cash_in": cash_in,
                "cash_out": cash_out, "expected_cash": expected_cash, "difference": diff}


class Payment(models.Model):
    class InvoiceStatus(models.TextChoices):
        NONE = "none", "No facturable"
        PENDING = "pending", "Pendiente"
        SENT = "sent", "Enviado"
        AUTHORIZED = "authorized", "Autorizado"
        ERROR = "error", "Error"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="payments", verbose_name="socio")
    charge = models.ForeignKey(Charge, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments",
                               verbose_name="cargo")
    amount = models.DecimalField("importe", max_digits=12, decimal_places=2)
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name="medio de pago")
    paid_at = models.DateTimeField("fecha", default=timezone.now)
    reference = models.CharField("referencia", max_length=120, blank=True)
    notes = models.CharField("notas", max_length=200, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    cash_session = models.ForeignKey(CashSession, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="payments")
    is_void = models.BooleanField("anulado", default=False)
    external_id = models.CharField(max_length=120, blank=True, db_index=True)

    invoice_status = models.CharField(max_length=12, choices=InvoiceStatus.choices, default=InvoiceStatus.NONE)
    invoice_number = models.CharField(max_length=40, blank=True)
    invoice_cae = models.CharField(max_length=40, blank=True)
    invoice_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-paid_at",)
        verbose_name = "pago"
        verbose_name_plural = "pagos"

    def __str__(self):
        return f"{self.member} · ${self.amount}"


class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = "rent", "Alquiler"
        SALARIES = "salaries", "Sueldos / honorarios"
        SERVICES = "services", "Servicios"
        EQUIPMENT = "equipment", "Equipamiento"
        MAINTENANCE = "maintenance", "Mantenimiento"
        MARKETING = "marketing", "Publicidad"
        TAXES = "taxes", "Impuestos"
        OTHER = "other", "Otros"

    date = models.DateField("fecha", default=timezone.localdate)
    category = models.CharField("categoría", max_length=12, choices=Category.choices, default=Category.OTHER)
    description = models.CharField("descripción", max_length=200)
    amount = models.DecimalField("importe", max_digits=12, decimal_places=2)
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name="medio de pago")
    cash_session = models.ForeignKey(CashSession, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="expenses")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("-date", "-id")
        verbose_name = "gasto"
        verbose_name_plural = "gastos"

    def __str__(self):
        return self.description
