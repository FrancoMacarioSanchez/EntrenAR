"""API CoreX (Hub -> EntrenAR). Se monta en el urlconf público como /corex/v1/."""
from django.urls import path

from . import corex_api as v

urlpatterns = [
    path("health/", v.health),
    path("tenants/", v.tenants),
    path("tenants/<str:schema>/", v.tenant_detail),
    path("tenants/<str:schema>/metricas/", v.metrics),
    path("tenants/<str:schema>/suspender/", v.suspend),
    path("tenants/<str:schema>/reactivar/", v.reactivate),
    path("tenants/<str:schema>/plan/", v.plan),
]
