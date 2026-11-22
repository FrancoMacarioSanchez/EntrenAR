from django.urls import path

from . import views_addons as ad
from . import views
from . import views_billing as b
from . import views_classes as cl
from . import views_crm as crm
from . import views_frontdesk as fd
from . import views_members as mb
from .cruds import CRUDS

app_name = "panel"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("notificaciones/", views.notifications, name="notifications"),
    path("buscar/", views.global_search, name="search"),

    # socios
    path("socios/", mb.member_list, name="members"),
    path("socios/nuevo/", mb.member_form, name="member_create"),
    path("socios/buscar.json", mb.member_search_json, name="member_search"),
    path("socios/<int:pk>/", mb.member_detail, name="member_detail"),
    path("socios/<int:pk>/editar/", mb.member_form, name="member_update"),
    path("socios/<int:pk>/eliminar/", mb.member_delete, name="member_delete"),
    path("socios/<int:pk>/nota/", mb.member_note, name="member_note"),
    path("socios/<int:pk>/acceso-app/", mb.member_app_access, name="member_app_access"),
    path("socios/<int:pk>/carnet/", mb.member_card, name="member_card"),

    # membresías
    path("membresias/vender/", mb.sell, name="sell"),
    path("membresias/<int:pk>/congelar/", mb.membership_freeze, name="membership_freeze"),
    path("membresias/<int:pk>/renovar/", mb.membership_renew, name="membership_renew"),
    path("membresias/<int:pk>/cancelar/", mb.membership_cancel, name="membership_cancel"),
    path("membresias/<int:pk>/auto-renovacion/", mb.membership_toggle_renew, name="membership_toggle_renew"),

    # cobros
    path("cobros/", b.debts, name="debts"),
    path("cobros/socio/<int:member_id>/", b.collect, name="collect"),
    path("pagos/", b.payments, name="payments"),
    path("pagos/<int:pk>/anular/", b.payment_void, name="payment_void"),
    path("pagos/<int:pk>/facturar/", b.payment_invoice, name="payment_invoice"),
    path("pagos/<int:pk>/recibo/", b.receipt, name="receipt"),
    path("cargos/<int:pk>/mercadopago/", b.charge_mp_link, name="charge_mp"),
    path("cargos/<int:pk>/anular/", b.charge_cancel, name="charge_cancel"),
    path("caja/", b.cash, name="cash"),
    path("caja/<int:pk>/", b.cash_detail, name="cash_detail"),

    # recepción
    path("checkin/", fd.checkin_screen, name="checkin"),
    path("checkin/registrar/", fd.checkin_submit, name="checkin_submit"),
    path("checkin/vista/<int:pk>/", fd.checkin_preview, name="checkin_preview"),
    path("checkin/recientes/", fd.recent_checkins, name="checkin_recent"),
    path("checkin/qr/", fd.qr_poster, name="qr_poster"),
    path("checkin/pantalla/", fd.qr_screen, name="qr_screen"),
    path("checkin/pantalla/token/", fd.qr_screen_token, name="qr_screen_token"),

    # clases
    path("clases/", cl.schedule, name="classes"),
    path("clases/<int:pk>/<str:date>/", cl.class_day, name="class_day"),
    path("clases/<int:pk>/<str:date>/todos/", cl.class_mark_all, name="class_mark_all"),

    # CRM
    path("crm/", crm.pipeline, name="pipeline"),
    path("crm/leads/<int:pk>/", crm.lead_detail, name="lead_detail"),
    path("crm/leads/<int:pk>/mover/", crm.lead_move, name="lead_move"),
    path("crm/retencion/", crm.retention, name="retention"),
    path("crm/mis-tareas/", crm.my_tasks, name="my_tasks"),
    path("crm/tareas/<int:pk>/toggle/", crm.task_toggle, name="task_toggle"),
    path("crm/campanas/<int:pk>/enviar/", crm.campaign_run, name="campaign_run"),

    # administración
    path("reportes/", views.reports, name="reports"),
    path("gerencia/", views.management, name="management"),
    path("auditoria/", views.audit, name="audit"),
    path("configuracion/", views.settings_view, name="settings"),
    path("configuracion/complementos/", ad.addons, name="addons"),
    path("socios/<int:pk>/ia/", ad.member_ai_limit, name="member_ai_limit"),
    path("cuenta/suscripcion/", views.subscription, name="subscription"),
    path("cuenta/password/", views.password_change, name="password"),
    path("cuenta/activar/<uidb64>/<token>/", views.activate_account, name="activate"),
    path("cuenta/exportar/", views.export_all, name="export"),
]

for crud in CRUDS:
    urlpatterns += crud.urls()
