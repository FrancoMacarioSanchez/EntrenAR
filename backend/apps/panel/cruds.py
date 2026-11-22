"""Declaración de los ABM del panel."""
from django import forms
from django.urls import reverse
from django.utils.html import format_html

from apps.accounts.models import User
from apps.accounts.perms import ALL as PERM_ALL
from apps.accounts.perms import LABELS as PERM_LABELS
from apps.accounts.perms import PERMISSION_GROUPS, PRESETS
from apps.billing.models import Charge, Expense, PaymentMethod
from apps.classes.models import GymClass
from apps.crm.models import Campaign, Lead, MessageTemplate, Task
from apps.memberships.models import Plan, Promotion
from apps.training.models import Exercise, Routine

from .crud import Crud
from .forms_utils import StyledModelForm, styled_formfield


class PlanCrud(Crud):
    perm = "plans"
    model = Plan
    slug = "planes"
    exclude = ()
    fields = ["name", "description", "period", "duration_count", "price", "access_type", "visits_limit",
              "includes_classes", "includes_routine", "color", "is_active", "order"]
    columns = [("", "color", "color"), ("Plan", "name"), ("Período", "period"), ("Precio", "price", "money"),
               ("Acceso", "access_type"), ("Límite", "visits_limit"), ("Clases", "includes_classes"),
               ("Activo", "is_active")]
    search_fields = ["name"]
    filters = ["period", "is_active"]
    help_text = "Los planes son lo que vendés a tus socios. Cambiar el precio no afecta membresías ya vendidas."


class PromotionForm(StyledModelForm):
    class Meta:
        model = Promotion
        fields = ["name", "description", "kind", "value", "plans", "starts_on", "ends_on", "code", "only_new_members",
                  "max_uses", "show_in_app", "color", "is_active"]
        formfield_callback = styled_formfield
        widgets = {"plans": forms.CheckboxSelectMultiple}

    def clean(self):
        c = super().clean()
        if c.get("kind") == "percent" and c.get("value") and c["value"] > 100:
            self.add_error("value", "El descuento no puede superar el 100%.")
        if c.get("ends_on") and c.get("starts_on") and c["ends_on"] < c["starts_on"]:
            self.add_error("ends_on", "La fecha de fin es anterior al inicio.")
        return c


class PromotionCrud(Crud):
    model = Promotion
    perm = "promotions"
    slug = "promociones"
    form_class = PromotionForm
    columns = [("", "color", "color"), ("Promoción", "name"), ("Beneficio", "summary"),
               ("Planes", lambda o: ", ".join(p.name for p in o.plans.all()) or "Todos"),
               ("Vigencia", lambda o: f"{o.starts_on:%d/%m}" + (f" al {o.ends_on:%d/%m/%Y}" if o.ends_on else " · sin fin")),
               ("Usos", lambda o: f"{o.uses}" + (f"/{o.max_uses}" if o.max_uses else "")),
               ("Vigente", lambda o: o.is_current())]
    search_fields = ["name", "code"]
    filters = ["kind", "is_active"]
    help_text = ("Las promociones se eligen al vender una membresía. Podés limitarlas por plan, fecha, socios nuevos "
                 "o cantidad de usos, y mostrarlas en la app de los alumnos.")

    def get_queryset(self, request):
        return Promotion.objects.prefetch_related("plans")


class PaymentMethodCrud(Crud):
    perm = "payment_methods"
    model = PaymentMethod
    slug = "medios-de-pago"
    fields = ["name", "kind", "is_invoiceable", "surcharge_percent", "is_active", "order"]
    columns = [("Nombre", "name"), ("Tipo", "kind"), ("Se factura", "is_invoiceable"),
               ("Recargo %", "surcharge_percent"), ("Activo", "is_active")]


class ExpenseCrud(Crud):
    perm = "expenses"
    model = Expense
    slug = "gastos"
    fields = ["date", "category", "description", "amount", "method"]
    columns = [("Fecha", "date"), ("Categoría", "category"), ("Descripción", "description"),
               ("Importe", "amount", "money"), ("Medio", "method__name")]
    search_fields = ["description"]
    filters = ["category", "method"]

    def save_form(self, request, form, creating):
        from apps.billing.models import CashSession

        obj = form.save(commit=False)
        if creating:
            obj.created_by = request.user
            obj.cash_session = CashSession.current()
        obj.save()
        return obj


class ChargeForm(StyledModelForm):
    class Meta:
        model = Charge
        fields = ["member", "kind", "concept", "amount", "due_date"]
        formfield_callback = styled_formfield


class ChargeCrud(Crud):
    perm = "collect"
    model = Charge
    slug = "cargos"
    form_class = ChargeForm
    title = "Cargo"
    columns = [("Socio", "member"), ("Concepto", "concept"), ("Tipo", "kind"), ("Vence", "due_date"),
               ("Importe", "amount", "money"), ("Saldo", "balance", "money"), ("Estado", "status")]
    search_fields = ["member__first_name", "member__last_name", "member__dni", "concept"]
    filters = ["status", "kind"]
    can_delete = False
    help_text = "Cargá productos, servicios u otros conceptos para cobrarle a un socio."

    def get_queryset(self, request):
        return Charge.objects.select_related("member")

    def get_form_kwargs(self, request, obj=None):
        return {} if obj else {"initial": {"member": request.GET.get("member")}}

    def detail_url(self, obj):
        return reverse("panel:member_detail", args=[obj.member_id]) + "?tab=cobros"


class GymClassCrud(Crud):
    perm = "classes_manage"
    model = GymClass
    slug = "clases-abm"
    title = "Clase"
    title_plural = "Clases (horarios)"
    fields = ["name", "description", "trainer", "weekday", "start_time", "duration_min", "capacity", "room", "color",
              "booking_opens_hours", "cancel_limit_hours", "is_active"]
    columns = [("", "color", "color"), ("Actividad", "name"), ("Día", "weekday"), ("Hora", "start_time"),
               ("Profesor", "trainer"), ("Cupo", "capacity"), ("Sala", "room"), ("Activa", "is_active")]
    filters = ["weekday", "trainer", "is_active"]
    search_fields = ["name"]

    def success_url(self, obj):
        return reverse("panel:classes")


class LeadForm(StyledModelForm):
    class Meta:
        model = Lead
        fields = ["name", "phone", "email", "source", "stage", "interest", "goal", "assigned_to", "trial_date",
                  "next_contact", "value", "referred_by", "lost_reason", "notes"]
        formfield_callback = styled_formfield

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["assigned_to"].queryset = User.objects.exclude(role="student")


class LeadCrud(Crud):
    perm = "crm"
    model = Lead
    slug = "leads"
    form_class = LeadForm
    columns = [("Nombre", "name"), ("Teléfono", "phone"), ("Origen", "source"), ("Etapa", "stage"),
               ("Interés", "interest"), ("Responsable", "assigned_to"), ("Próx. contacto", "next_contact"),
               ("Alta", "created_at")]
    search_fields = ["name", "phone", "email"]
    filters = ["stage", "source", "assigned_to"]

    def detail_url(self, obj):
        return reverse("panel:lead_detail", args=[obj.pk])

    def success_url(self, obj):
        return reverse("panel:lead_detail", args=[obj.pk])


class TaskForm(StyledModelForm):
    class Meta:
        model = Task
        fields = ["title", "due_date", "priority", "assigned_to", "member", "lead", "done"]
        formfield_callback = styled_formfield

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["assigned_to"].queryset = User.objects.exclude(role="student")


class TaskCrud(Crud):
    model = Task
    slug = "tareas"
    form_class = TaskForm
    columns = [("Tarea", "title"), ("Vence", "due_date"), ("Prioridad", "priority"), ("Responsable", "assigned_to"),
               ("Socio", "member"), ("Lead", "lead"), ("Hecha", "done")]
    search_fields = ["title"]
    filters = ["done", "priority", "assigned_to"]

    def get_queryset(self, request):
        return Task.objects.select_related("member", "lead", "assigned_to")


class TemplateCrud(Crud):
    perm = "templates"
    model = MessageTemplate
    slug = "plantillas"
    fields = ["name", "channel", "subject", "body"]
    columns = [("Nombre", "name"), ("Canal", "channel"), ("Mensaje", lambda o: o.body[:90])]


class CampaignCrud(Crud):
    perm = "campaigns"
    model = Campaign
    slug = "campanas"
    fields = ["name", "segment", "template"]
    columns = [("Campaña", "name"), ("Segmento", "segment"), ("Plantilla", "template"), ("Enviada", "sent_at"),
               ("Destinatarios", "sent_count")]

    def detail_url(self, obj):
        return reverse("panel:campaign_run", args=[obj.pk])


class ExerciseCrud(Crud):
    perm = "exercises"
    model = Exercise
    slug = "ejercicios"
    fields = ["name", "muscle_group", "secondary_muscles", "equipment", "tracking", "instructions", "video_url",
              "image", "is_active"]
    columns = [("Ejercicio", "name"), ("Grupo", "muscle_group"), ("Equipamiento", "equipment"),
               ("Registro", "tracking"), ("Video", lambda o: bool(o.video_url)), ("Activo", "is_active")]
    search_fields = ["name", "secondary_muscles"]
    filters = ["muscle_group", "equipment", "is_active"]
    per_page = 50


class RoutineCrud(Crud):
    perm = "routines_view"
    model = Routine
    slug = "rutinas"
    can_create = False
    can_edit = False
    columns = [("Rutina", "name"), ("Alumno", "member"), ("Entrenador", "trainer"), ("Desde", "start_date"),
               ("Versión", "version"), ("Activa", "is_active"), ("Plantilla", "is_template"),
               ("Días", lambda o: o.days.count())]
    search_fields = ["name", "member__first_name", "member__last_name"]
    filters = ["is_active", "is_template", "trainer"]
    help_text = "Las rutinas se arman desde la app del entrenador (constructor con ejercicios, series y repeticiones)."

    def get_queryset(self, request):
        return Routine.objects.select_related("member", "trainer")

    def detail_url(self, obj):
        return f"/app/entrenador/rutinas/{obj.pk}"


# ----------------------------------------------------------------- staff y permisos
class StaffForm(StyledModelForm):
    password = forms.CharField(label="Contraseña", required=False, widget=forms.PasswordInput,
                               help_text="Dejar vacío para no cambiarla.")
    perms = forms.MultipleChoiceField(label="Permisos", required=False, widget=forms.CheckboxSelectMultiple,
                                      choices=[(c, PERM_LABELS[c]) for c in PERM_ALL])

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "specialties", "bio", "avatar",
                  "is_active", "custom_permissions"]
        formfield_callback = styled_formfield

    def __init__(self, *a, editor=None, **kw):
        super().__init__(*a, **kw)
        self.editor = editor
        allowed = [c for c in User.Role.choices if c[0] != "student"]
        if not (editor and editor.is_owner):
            allowed = [c for c in allowed if c[0] != "owner"]
        self.fields["role"].choices = allowed
        self.fields["custom_permissions"].label = "Personalizar los permisos de este usuario"
        self.fields["perms"].initial = sorted(self.instance.perm_codes()) if self.instance.pk else PRESETS["reception"]
        if not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = ""

    def clean(self):
        c = super().clean()
        if self.instance.pk and self.instance.is_owner and not (self.editor and self.editor.is_owner):
            raise forms.ValidationError("Solo el dueño puede modificar a otro dueño.")
        if self.editor and not self.editor.is_owner and "staff" in (c.get("perms") or []) and c.get("custom_permissions"):
            raise forms.ValidationError("Solo el dueño puede dar el permiso de administrar el staff.")
        return c

    def save(self, commit=True):
        u = super().save(commit=False)
        if self.cleaned_data.get("password"):
            u.set_password(self.cleaned_data["password"])
        u.permissions = sorted(set(self.cleaned_data.get("perms") or [])) if u.custom_permissions else []
        if u.role == "owner":
            u.custom_permissions = False
        if commit:
            u.save()
        return u

    def perm_groups(self):
        chosen = set(self["perms"].value() or [])
        return [(title, [(code, label, code in chosen) for code, label in items]) for title, items in PERMISSION_GROUPS]


class StaffCrud(Crud):
    model = User
    perm = "staff"
    slug = "staff"
    title = "Usuario del staff"
    title_plural = "Staff y permisos"
    form_class = StaffForm
    form_template = "panel/staff_form.html"
    can_delete = False
    columns = [("Usuario", "username"), ("Nombre", lambda o: o.get_full_name()), ("Rol", "role"),
               ("Permisos", lambda o: "Todos" if o.is_owner else (f"{len(o.perm_codes())} personalizados"
                                                                   if o.custom_permissions else "Estándar del rol")),
               ("Alumnos", lambda o: o.students.count() if o.role == "trainer" else ""),
               ("Último ingreso", "last_login"), ("Activo", "is_active")]
    search_fields = ["username", "first_name", "last_name", "email"]
    filters = ["role", "is_active"]
    help_text = ("El dueño tiene acceso a todo. Para el resto podés usar los permisos estándar de su rol o elegir "
                 "uno por uno qué puede ver y hacer. Los entrenadores trabajan desde la app (/app).")

    def get_queryset(self, request):
        return User.objects.exclude(role="student").exclude(is_support=True).order_by("role", "first_name")

    def get_form_kwargs(self, request, obj=None):
        return {"editor": request.user}

    def save_form(self, request, form, creating):
        from django.core.exceptions import PermissionDenied

        from apps.tenants.models import Gym

        if creating:
            gym = Gym.objects.get(schema_name=request.tenant.schema_name)
            active = self.get_queryset(request).filter(is_active=True).count()
            if gym.max_staff and active >= gym.max_staff:
                raise PermissionDenied("Llegaste al máximo de usuarios de tu plan. Mejorá el plan para sumar más.")
        return form.save()


def staff_badge(user):
    return format_html('<span class="badge">{}</span>', user.get_role_display())


CRUDS = [PlanCrud(), PromotionCrud(), PaymentMethodCrud(), ExpenseCrud(), ChargeCrud(), GymClassCrud(), LeadCrud(), TaskCrud(),
         TemplateCrud(), CampaignCrud(), ExerciseCrud(), RoutineCrud(), StaffCrud()]
