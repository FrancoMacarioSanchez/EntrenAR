"""URLs del schema público: landing, alta de gimnasios, admin de CoreX, API CoreX (Hub) y healthcheck."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from apps.tenants import public_views
from apps.tenants.admin_costs import costs_view
from apps.tenants.public_fallback import api_no_tenant, app_no_tenant

urlpatterns = [
    path("", public_views.landing, name="landing"),
    path("registro/", public_views.signup, name="signup"),
    path("registro/listo/<slug:slug>/", public_views.signup_done, name="signup_done"),
    path("corex-admin/costos/", admin.site.admin_view(costs_view), name="admin_costs"),
    path("corex-admin/", admin.site.urls),
    path("corex/v1/", include("apps.tenants.corex_urls")),
    path("healthz/", public_views.healthz, name="healthz"),
    re_path(r"^api/v1/(?P<path>.*)$", api_no_tenant),
    re_path(r"^app(?:/(?P<path>.*))?$", app_no_tenant),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
