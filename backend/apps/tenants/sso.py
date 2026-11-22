"""Ingreso único desde CoreX Hub (token firmado, un solo uso, vence en HUB_SSO_MAX_AGE)."""
from django.conf import settings
from django.contrib.auth import login
from django.core import signing
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .models import UsedSSOToken


def hub_sso(request):
    if not settings.HUB_SSO_SECRET:
        return HttpResponseForbidden("SSO no configurado.")
    try:
        data = signing.loads(request.GET.get("token", ""), key=settings.HUB_SSO_SECRET,
                             salt="corex-hub-sso", max_age=settings.HUB_SSO_MAX_AGE)
    except signing.BadSignature:
        return HttpResponseForbidden("Token inválido o vencido.")
    if data.get("tenant") != request.tenant.slug or not data.get("jti"):
        return HttpResponseForbidden("Token de otro gimnasio.")
    try:
        UsedSSOToken.objects.create(jti=data["jti"])
    except IntegrityError:
        return HttpResponseForbidden("Token ya utilizado.")

    from apps.accounts.models import User
    from apps.core.models import AuditLog

    if data.get("mode") == "support":
        staff = (data.get("staff") or "corex").lower()
        user, _ = User.objects.get_or_create(
            username=f"soporte.{staff}",
            defaults={"role": User.Role.ADMIN, "is_support": True, "first_name": "Soporte", "last_name": "CoreX"},
        )
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=["password"])
    else:
        user = User.objects.filter(username=data.get("username"), is_active=True).first()
        if not user:
            return HttpResponseForbidden("Usuario inexistente en este gimnasio.")
    login(request, user, backend="apps.accounts.backends.FlexibleLoginBackend")
    AuditLog.log(user, "sso", f"Ingreso desde CoreX Hub ({data.get('mode', 'user')})")
    nxt = data.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    if user.is_student or user.is_trainer:
        nxt = "/app/"
    return redirect(nxt)
