from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import PaymentMethod
from apps.core.models import GymSettings
from apps.members.models import Member
from apps.memberships.models import Plan, Promotion

from .forms_utils import StyledForm, StyledModelForm, styled_formfield


class MemberForm(StyledModelForm):
    create_app_access = forms.BooleanField(label="Crear acceso a la app (usuario: DNI, contraseña: DNI)",
                                           required=False, initial=True)

    class Meta:
        model = Member
        fields = ["first_name", "last_name", "dni", "email", "phone", "birth_date", "sex", "height_cm", "address",
                  "photo", "goal", "trainer", "status", "emergency_name", "emergency_phone", "medical_notes",
                  "medical_clearance_until", "medical_clearance_file", "joined_at", "source", "notes"]
        formfield_callback = styled_formfield

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["trainer"].queryset = User.objects.filter(role=User.Role.TRAINER, is_active=True)
        if self.instance.pk:
            self.fields.pop("create_app_access")

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip().replace(".", "")
        return dni or None


class SellMembershipForm(StyledForm):
    member = forms.ModelChoiceField(label="Socio", queryset=Member.objects.all())
    plan = forms.ModelChoiceField(label="Plan", queryset=Plan.objects.filter(is_active=True))
    start_date = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}),
                                 help_text="Vacío = continúa la membresía actual o empieza hoy")
    discount_percent = forms.DecimalField(label="Descuento manual (%)", required=False, min_value=0, max_value=100,
                                          initial=0)
    promotion = forms.ModelChoiceField(label="Promoción", queryset=Promotion.objects.none(), required=False,
                                       empty_label="Sin promoción")
    auto_renew = forms.BooleanField(label="Renovación automática", required=False)
    charge_enrollment = forms.BooleanField(label="Cobrar matrícula", required=False)
    pay_now = forms.BooleanField(label="Registrar el pago ahora", required=False, initial=True)
    pay_method = forms.ModelChoiceField(label="Medio de pago", queryset=PaymentMethod.objects.filter(is_active=True),
                                        required=False)
    pay_amount = forms.DecimalField(label="Importe recibido", required=False,
                                    help_text="Vacío = total. Si es menor queda saldo pendiente.")
    notes = forms.CharField(label="Notas", required=False)

    def __init__(self, *a, user=None, **kw):
        super().__init__(*a, **kw)
        self.fields["auto_renew"].initial = GymSettings.get().auto_renew_default
        today = timezone.localdate()
        self.fields["promotion"].queryset = Promotion.objects.filter(is_active=True, starts_on__lte=today).exclude(
            ends_on__lt=today)
        if user is not None and not user.can("discounts"):
            del self.fields["discount_percent"]
        if user is not None and not user.can("promotions_apply"):
            del self.fields["promotion"]

    def clean(self):
        c = super().clean()
        if c.get("pay_now") and not c.get("pay_method"):
            self.add_error("pay_method", "Elegí el medio de pago.")
        promo, member, plan = c.get("promotion"), c.get("member"), c.get("plan")
        if promo and member and plan:
            problem = promo.problem_for(plan, member)
            if problem:
                self.add_error("promotion", problem)
        return c


class PaymentForm(StyledForm):
    amount = forms.DecimalField(label="Importe", min_value=0.01)
    method = forms.ModelChoiceField(label="Medio de pago", queryset=PaymentMethod.objects.filter(is_active=True))
    reference = forms.CharField(label="Referencia / comprobante", required=False)
    notes = forms.CharField(label="Notas", required=False)


class FreezeForm(StyledForm):
    start_date = forms.DateField(label="Desde", widget=forms.DateInput(attrs={"type": "date"}),
                                 initial=timezone.localdate)
    end_date = forms.DateField(label="Hasta", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label="Motivo", required=False)


class CashOpenForm(StyledForm):
    opening_amount = forms.DecimalField(label="Efectivo inicial en caja", min_value=0, initial=0)


class CashCloseForm(StyledForm):
    closing_amount = forms.DecimalField(label="Efectivo contado", min_value=0)
    notes = forms.CharField(label="Notas", required=False)


class GymSettingsForm(StyledModelForm):
    class Meta:
        model = GymSettings
        exclude = ("checkin_key",)
        formfield_callback = styled_formfield
        widgets = {"mp_access_token": forms.PasswordInput(render_value=True),
                   "arca_webhook_token": forms.PasswordInput(render_value=True)}


class NoteForm(StyledForm):
    text = forms.CharField(label="Nota", widget=forms.Textarea(attrs={"rows": 2}))
    visible_to_member = forms.BooleanField(label="Visible para el alumno", required=False)
