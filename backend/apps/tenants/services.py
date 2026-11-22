"""Alta y arranque de gimnasios (tenants)."""
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from .models import Domain, Gym, SaasPlan

RESERVED = {"www", "public", "admin", "api", "app", "hub", "static", "media", "corex", "mail"}


def make_schema_name(slug):
    s = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    if not s or s[0].isdigit():
        s = f"g_{s}"
    return s[:60]


def unique_slug(name):
    base = slugify(name)[:40] or "gimnasio"
    if base in RESERVED:
        base = f"{base}-gym"
    slug, i = base, 2
    while Gym.objects.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


def create_gym(*, name, admin_username, admin_email="", admin_password=None, admin_name="",
               slug=None, plan_code=None, cuit="", phone="", trial_days=None, status=None,
               current_period_end=None, hub_ref=None, demo=False, schema_name=None, invite=False):
    """Crea schema + dominio + usuario dueño + configuración inicial. Devuelve (gym, password).

    Con `invite=True` el dueño se crea sin contraseña (se le manda un link para definirla) y password es None.
    """
    slug = slug or unique_slug(name)
    if slug in RESERVED:
        raise ValueError("Ese nombre de subdominio está reservado.")
    plan = SaasPlan.objects.filter(code=plan_code).first() if plan_code else SaasPlan.objects.filter(is_active=True).first()
    trial_days = settings.SAAS_TRIAL_DAYS if trial_days is None else trial_days

    gym = Gym(
        schema_name=schema_name or make_schema_name(slug), slug=slug, name=name, cuit=cuit, phone=phone,
        email=admin_email, plan=plan, hub_ref=hub_ref,
        status=status or Gym.Status.TRIALING,
        trial_ends_at=timezone.now() + timedelta(days=trial_days),
        current_period_end=current_period_end,
    )
    gym.save()  # crea el schema y corre las migraciones del tenant
    Domain.objects.create(domain=f"{slug}.{settings.BASE_DOMAIN}", tenant=gym, is_primary=True)

    with tenant_context(gym):
        password = bootstrap_gym(gym, admin_username, admin_email, admin_password, admin_name, invite=invite)
        if demo:
            from apps.core.demo import load_demo_data
            load_demo_data()

    return gym, password


@transaction.atomic
def bootstrap_gym(gym, username, email, password, full_name, invite=False):
    from apps.accounts.models import User
    from apps.billing.models import PaymentMethod
    from apps.core.models import GymSettings
    from apps.memberships.models import Plan
    from apps.training.seed import seed_exercises

    GymSettings.objects.get_or_create(pk=1, defaults={"display_name": gym.name, "phone": gym.phone, "email": gym.email})

    for i, (n, kind, inv) in enumerate([
        ("Efectivo", "cash", False), ("Transferencia", "transfer", True), ("Tarjeta de débito", "card", True),
        ("Tarjeta de crédito", "card", True), ("Mercado Pago", "mercadopago", True),
    ]):
        PaymentMethod.objects.get_or_create(name=n, defaults={"kind": kind, "is_invoiceable": inv, "order": i})

    if not Plan.objects.exists():
        Plan.objects.create(name="Pase libre mensual", period=Plan.Period.MONTH, price=35000, color="#22c55e")
        Plan.objects.create(name="3 veces por semana", period=Plan.Period.MONTH, price=28000,
                            access_type=Plan.Access.WEEKLY, visits_limit=3, color="#3b82f6")
        Plan.objects.create(name="Pase diario", period=Plan.Period.DAY, price=5000, color="#f59e0b")
        Plan.objects.create(name="Trimestral pase libre", period=Plan.Period.QUARTER, price=95000, color="#a855f7")

    seed_exercises()

    import secrets
    password = None if invite else (password or secrets.token_urlsafe(8))
    first, _, last = (full_name or "").partition(" ")
    if not User.objects.filter(username=username).exists():
        User.objects.create_user(username=username, email=email, password=password, first_name=first,
                                 last_name=last, role=User.Role.OWNER, is_staff=True)
    return password


def invite_link(gym, username):
    """Link de un solo uso para que el dueño defina su contraseña (vence según PASSWORD_RESET_TIMEOUT)."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from apps.accounts.models import User

    with tenant_context(gym):
        user = User.objects.get(username=username)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        email = user.email
    return f"{gym.primary_url()}/cuenta/activar/{uid}/{token}/", email


def invite_owner(gym, username):
    """Manda el email de bienvenida con el link. Devuelve (enviado, link)."""
    from django.core.mail import send_mail

    link, email = invite_link(gym, username)
    if not email:
        return False, link
    body = (f"¡Hola! Ya está listo el panel de {gym.name} en EntrenAR.\n\n"
            f"Usuario: {username}\n"
            f"Definí tu contraseña acá (el link vence en {settings.PASSWORD_RESET_TIMEOUT // 86400} días):\n{link}\n\n"
            f"Después vas a entrar en {gym.primary_url()}/login/\n\n— Equipo CoreX")
    try:
        send_mail(f"Tu gimnasio {gym.name} ya está en EntrenAR", body, None, [email])
        return True, link
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("No se pudo mandar la invitación de %s", gym)
        return False, link
