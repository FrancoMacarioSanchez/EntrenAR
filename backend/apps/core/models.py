from django.conf import settings
from django.db import models

from .utils import TenantPath, new_checkin_key


class GymSettings(models.Model):
    """Configuración del gimnasio (una fila por schema)."""
    display_name = models.CharField("nombre visible", max_length=120)
    logo = models.ImageField(upload_to=TenantPath("branding"), null=True, blank=True)
    primary_color = models.CharField("color principal", max_length=9, default="#ff5a1f")
    accent_color = models.CharField("color de acento", max_length=9, default="#111827")
    address = models.CharField("dirección", max_length=200, blank=True)
    phone = models.CharField("teléfono", max_length=40, blank=True)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    instagram = models.CharField(max_length=80, blank=True)
    opening_hours = models.CharField("horarios", max_length=200, blank=True, default="Lun a Vie 7 a 23 · Sáb 9 a 14")

    # Reglas de negocio
    enrollment_fee = models.DecimalField("matrícula (primera inscripción)", max_digits=12, decimal_places=2, default=0)
    late_fee_percent = models.DecimalField("recargo por mora (%)", max_digits=5, decimal_places=2, default=0)
    late_fee_after_days = models.PositiveSmallIntegerField("aplicar recargo a los X días", default=10)
    access_grace_days = models.PositiveSmallIntegerField("días de tolerancia para ingresar con cuota vencida", default=3)
    block_access_with_debt = models.BooleanField("bloquear ingreso con deuda", default=True)
    require_medical_clearance = models.BooleanField("exigir apto físico vigente", default=False)
    auto_renew_default = models.BooleanField("renovación automática por defecto", default=True)
    inactivity_alert_days = models.PositiveSmallIntegerField("alerta de abandono (días sin venir)", default=10)
    expiry_notice_days = models.PositiveSmallIntegerField("avisar vencimiento X días antes", default=5)
    trainers_see_all_members = models.BooleanField("los entrenadores ven a todos los alumnos", default=True)
    students_can_edit_routine = models.BooleanField("los alumnos pueden modificar su rutina", default=False)

    # Autoingreso con QR (el socio escanea el QR del gimnasio con su celular)
    self_checkin_enabled = models.BooleanField("permitir ingreso escaneando el QR del gimnasio", default=True)
    checkin_key = models.CharField("clave del QR de ingreso", max_length=40, default=new_checkin_key)
    checkin_require_location = models.BooleanField(
        "exigir estar en el gimnasio (ubicación) con el QR impreso", default=False,
        help_text="Evita que alguien use una foto del QR desde su casa. La pantalla con QR rotativo no lo necesita.")
    latitude = models.DecimalField("latitud del gimnasio", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("longitud del gimnasio", max_digits=9, decimal_places=6, null=True, blank=True)
    checkin_radius_m = models.PositiveSmallIntegerField("radio permitido (metros)", default=150)

    # Integraciones
    mp_access_token = models.CharField("Mercado Pago access token", max_length=200, blank=True)
    mp_public_key = models.CharField("Mercado Pago public key", max_length=200, blank=True)
    arca_enabled = models.BooleanField("facturar con ARCA", default=False)
    arca_webhook_url = models.URLField("URL del servicio de facturación", blank=True,
                                       help_text="EntrenAR envía un POST con los datos del comprobante (p. ej. FacturAR).")
    arca_webhook_token = models.CharField("token del servicio de facturación", max_length=200, blank=True)
    arca_point_of_sale = models.PositiveSmallIntegerField("punto de venta", default=1)
    arca_invoice_type = models.CharField("tipo de comprobante", max_length=2, default="C",
                                         choices=[("A", "Factura A"), ("B", "Factura B"), ("C", "Factura C")])

    # Mensajes
    welcome_message = models.TextField("mensaje de bienvenida (app)", blank=True,
                                       default="¡Bienvenido/a! Entrená fuerte y registrá cada serie 💪")

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"

    def __str__(self):
        return self.display_name

    @classmethod
    def get(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            obj = cls.objects.create(pk=1, display_name="Mi gimnasio")
        return obj


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)
    description = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @classmethod
    def log(cls, user, action, description):
        return cls.objects.create(user=user if getattr(user, "pk", None) else None, action=action,
                                  description=description[:300])


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=400, blank=True)
    url = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=30, default="info")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
