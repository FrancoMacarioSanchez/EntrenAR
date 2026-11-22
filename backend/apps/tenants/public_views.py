from django import forms
from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify

from .models import Gym, SaasPlan
from .services import RESERVED, create_gym


class SignupForm(forms.Form):
    gym_name = forms.CharField(label="Nombre del gimnasio", max_length=120)
    slug = forms.SlugField(label="Subdominio", max_length=40,
                           help_text=f"Tu gimnasio quedará en <subdominio>.{settings.BASE_DOMAIN}")
    plan = forms.ModelChoiceField(label="Plan", queryset=SaasPlan.objects.filter(is_active=True), required=False)
    full_name = forms.CharField(label="Tu nombre y apellido", max_length=120)
    email = forms.EmailField(label="Email")
    phone = forms.CharField(label="WhatsApp", max_length=40, required=False)
    username = forms.CharField(label="Usuario", max_length=60)
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput, min_length=8)

    def clean_slug(self):
        s = slugify(self.cleaned_data["slug"])
        if s in RESERVED or Gym.objects.filter(slug=s).exists():
            raise forms.ValidationError("Ese subdominio no está disponible.")
        return s


def landing(request):
    return render(request, "public/landing.html", {"plans": SaasPlan.objects.filter(is_active=True)})


def signup(request):
    if not settings.SAAS_ALLOW_SIGNUP:
        raise Http404
    form = SignupForm(request.POST or None, initial={"plan": request.GET.get("plan")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        gym, _ = create_gym(
            name=d["gym_name"], slug=d["slug"], plan_code=d["plan"].code if d["plan"] else None,
            admin_username=d["username"], admin_email=d["email"], admin_password=d["password"],
            admin_name=d["full_name"], phone=d.get("phone", ""),
        )
        return redirect("signup_done", slug=gym.slug)
    return render(request, "public/signup.html", {"form": form})


def signup_done(request, slug):
    gym = Gym.objects.filter(slug=slug).first()
    if not gym:
        raise Http404
    return render(request, "public/signup_done.html", {"gym": gym, "url": gym.primary_url()})


def healthz(request):
    """Para el monitoreo y el balanceador: verifica la base."""
    from django.db import connection

    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        return JsonResponse({"ok": True})
    except Exception as e:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(e)[:200]}, status=503)
