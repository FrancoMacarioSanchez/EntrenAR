"""URLs de cada gimnasio (schema del tenant)."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from apps.api.views_pwa import pwa_app, pwa_manifest
from apps.billing.views_webhooks import mercadopago_webhook
from apps.tenants.sso import hub_sso

urlpatterns = [
    path("", include("apps.panel.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("sso/hub/", hub_sso, name="hub_sso"),
    path("webhooks/mercadopago/", mercadopago_webhook, name="mp_webhook"),
    path("app/manifest.webmanifest", pwa_manifest, name="pwa_manifest"),
    re_path(r"^app(?:/(?P<path>.*))?$", pwa_app, name="pwa"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
