import secrets

from django.db import transaction

from apps.accounts.models import User


@transaction.atomic
def ensure_app_access(member, password=None):
    """Crea (o devuelve) el usuario de la app para un socio. Contraseña inicial = DNI."""
    if member.user_id:
        return member.user, None
    base = member.dni or (member.email.split("@")[0] if member.email else f"socio{member.pk}")
    username, i = base, 2
    while User.objects.filter(username=username).exists():
        username = f"{base}{i}"
        i += 1
    password = password or member.dni or secrets.token_urlsafe(6)
    user = User.objects.create_user(username=username, email=member.email, password=password,
                                    first_name=member.first_name, last_name=member.last_name,
                                    role=User.Role.STUDENT, must_change_password=True, phone=member.phone)
    member.user = user
    member.save(update_fields=["user"])
    return user, password
