import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django_tenants.admin import TenantAdminMixin

from .ai_billing import close_month, google_cost_ars, month_start
from .models import AIAddon, AIUsageMonth, Domain, Gym, HubEvent, InfraCost, SaasPlan


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


class AIAddonInline(admin.StackedInline):
    model = AIAddon
    extra = 0
    max_num = 1
    can_delete = False
    fieldsets = (
        ("Lo define CoreX", {"fields": ("allowed", "max_daily_limit", "price_per_1k_tokens")}),
        ("Lo define el gimnasio", {"fields": ("active", "daily_limit", "monthly_cap", "activated_at", "activated_by")}),
    )
    readonly_fields = ("activated_at", "activated_by")


@admin.register(Gym)
class GymAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "status", "state", "trial_ends_at", "current_period_end", "created_at")
    list_filter = ("status", "plan")
    search_fields = ("name", "slug", "cuit", "email", "hub_ref")
    inlines = [DomainInline, AIAddonInline]
    actions = ["send_to_hub", "resend_invite"]

    @admin.display(description="estado efectivo")
    def state(self, obj):
        return obj.effective_state

    @admin.action(description="Enviar estado y métricas (30 días) al Hub")
    def send_to_hub(self, request, queryset):
        from datetime import timedelta

        from django.utils import timezone

        from .hub_client import hub_enabled, process_pending, push_metrics, push_state
        if not hub_enabled():
            self.message_user(request, "Hub no configurado (HUB_URL / HUB_INGEST_TOKEN).", messages.ERROR)
            return
        today = timezone.localdate()
        for gym in queryset:
            push_state(gym)
            push_metrics(gym, [today - timedelta(days=i) for i in range(30)][::-1])
        ok, fail = process_pending()
        self.message_user(request, f"Enviados {ok} · fallidos {fail} (ver «Hub events»).")

    @admin.action(description="Reenviar invitación al dueño (definir contraseña)")
    def resend_invite(self, request, queryset):
        from django_tenants.utils import tenant_context

        from apps.accounts.models import User

        from .services import invite_owner
        for gym in queryset:
            with tenant_context(gym):
                owner = User.objects.filter(role=User.Role.OWNER).order_by("pk").first()
            if not owner:
                self.message_user(request, f"{gym}: no tiene dueño.", messages.WARNING)
                continue
            sent, link = invite_owner(gym, owner.username)
            self.message_user(request, f"{gym}: {'email enviado a ' + owner.email if sent else 'no se pudo enviar'}. "
                                       f"Link: {link}", messages.SUCCESS if sent else messages.WARNING)


@admin.register(SaasPlan)
class SaasPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "price_monthly", "max_members", "max_staff", "is_active")


class SentFilter(admin.SimpleListFilter):
    title, parameter_name = "envío", "sent"

    def lookups(self, request, model_admin):
        return (("yes", "Enviados"), ("pending", "Pendientes"), ("no", "Rechazados / agotados"))

    def queryset(self, request, qs):
        from .hub_client import MAX_ATTEMPTS
        if self.value() == "yes":
            return qs.filter(sent_at__isnull=False)
        if self.value() == "pending":
            return qs.filter(sent_at__isnull=True, attempts__lt=MAX_ATTEMPTS)
        if self.value() == "no":
            return qs.filter(sent_at__isnull=True, attempts__gte=MAX_ATTEMPTS)
        return qs


@admin.register(HubEvent)
class HubEventAdmin(admin.ModelAdmin):
    list_display = ("event", "tenant_slug", "attempts", "sent_at", "created_at", "short_error")
    list_filter = (SentFilter, "event")
    search_fields = ("tenant_slug",)
    readonly_fields = ("event_id", "event", "tenant_slug", "payload", "attempts", "next_try_at", "sent_at",
                       "last_error", "created_at")
    actions = ["retry"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="último error")
    def short_error(self, obj):
        return (obj.last_error or "")[:80]

    @admin.action(description="Reintentar ahora")
    def retry(self, request, queryset):
        from django.utils import timezone

        from .hub_client import process_pending
        n = queryset.filter(sent_at__isnull=True).update(attempts=0, next_try_at=timezone.now())
        ok, fail = process_pending()
        self.message_user(request, f"{n} reencolados · enviados {ok} · fallidos {fail}.")


@admin.register(InfraCost)
class InfraCostAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "currency", "amount", "share_pct", "ars", "since", "until")
    list_filter = ("category", "currency")
    list_editable = ("amount", "share_pct")

    @admin.display(description="por mes en ARS")
    def ars(self, obj):
        return obj.monthly_ars()


# ------------------------------------------------------------------ plug-in de IA

@admin.register(AIAddon)
class AIAddonAdmin(admin.ModelAdmin):
    list_display = ("gym", "allowed", "active", "max_daily_limit", "daily_limit", "price_per_1k_tokens",
                    "monthly_cap", "this_month")
    list_editable = ("allowed", "max_daily_limit", "price_per_1k_tokens")
    list_filter = ("allowed", "active")
    search_fields = ("gym__name", "gym__slug")
    readonly_fields = ("activated_at", "activated_by", "updated_at")
    fieldsets = (
        (None, {"fields": ("gym",)}),
        ("Lo define CoreX", {"fields": ("allowed", "max_daily_limit", "price_per_1k_tokens")}),
        ("Lo define el gimnasio (desde su panel)", {"fields": ("active", "daily_limit", "monthly_cap",
                                                               "activated_at", "activated_by", "updated_at")}),
    )

    @admin.display(description="este mes (ARS)")
    def this_month(self, obj):
        u = AIUsageMonth.objects.filter(gym=obj.gym, month=month_start()).first()
        return obj.cost_for(u.tokens) if u else 0


@admin.register(AIUsageMonth)
class AIUsageMonthAdmin(admin.ModelAdmin):
    list_display = ("gym", "month_label", "status", "requests", "tokens", "billed", "google_cost", "margin")
    list_filter = ("status", "month")
    search_fields = ("gym__name", "gym__slug")
    date_hierarchy = "month"
    readonly_fields = ("gym", "month", "requests", "tokens_in", "tokens_out", "status", "price_per_1k_tokens",
                       "amount", "closed_at", "hub_event")
    actions = ["close_selected", "close_without_sending", "export_csv"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="mes", ordering="month")
    def month_label(self, obj):
        return obj.month.strftime("%m/%Y")

    def _amount(self, obj):
        return obj.amount if obj.amount is not None else AIAddon.for_gym(obj.gym).cost_for(obj.tokens)

    @admin.display(description="a facturar (ARS)")
    def billed(self, obj):
        return f"{self._amount(obj)}{'' if obj.amount is not None else ' (estimado)'}"

    @admin.display(description="costo Google (ARS, est.)")
    def google_cost(self, obj):
        return google_cost_ars(obj.tokens_in, obj.tokens_out)

    @admin.display(description="margen")
    def margin(self, obj):
        billed, cost = self._amount(obj), google_cost_ars(obj.tokens_in, obj.tokens_out)
        return f"{round((billed - cost) / billed * 100)} %" if billed else "—"

    def _close(self, request, queryset, send):
        current = month_start()
        months = {u.month for u in queryset if u.status == AIUsageMonth.Status.OPEN and u.month < current}
        if not months:
            self.message_user(request, "No hay meses terminados abiertos en la selección (el mes en curso no se cierra).",
                              messages.WARNING)
            return
        gyms = {u.gym_id for u in queryset}
        closed = close_month(max(months), send=send, gyms=gyms)
        self.message_user(request, f"{len(closed)} períodos cerrados{' y enviados al Hub' if send else ''}.")

    @admin.action(description="Cerrar y enviar al Hub para facturar")
    def close_selected(self, request, queryset):
        self._close(request, queryset, send=True)

    @admin.action(description="Cerrar sin enviar (facturo a mano)")
    def close_without_sending(self, request, queryset):
        self._close(request, queryset, send=False)

    @admin.action(description="Exportar CSV")
    def export_csv(self, request, queryset):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="consumo_ia.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp, delimiter=";")
        w.writerow(["Gimnasio", "Slug", "CUIT", "Mes", "Estado", "Análisis", "Tokens entrada", "Tokens salida",
                    "Tokens", "Precio por 1.000", "Importe ARS", "Costo Google ARS (est.)"])
        for u in queryset.select_related("gym"):
            price = u.price_per_1k_tokens if u.price_per_1k_tokens is not None else AIAddon.for_gym(u.gym).price_per_1k_tokens
            w.writerow([u.gym.name, u.gym.slug, u.gym.cuit, u.month.strftime("%Y-%m"), u.get_status_display(), u.requests,
                        u.tokens_in, u.tokens_out, u.tokens, str(price).replace(".", ","),
                        str(self._amount(u)).replace(".", ","),
                        str(google_cost_ars(u.tokens_in, u.tokens_out)).replace(".", ",")])
        return resp
