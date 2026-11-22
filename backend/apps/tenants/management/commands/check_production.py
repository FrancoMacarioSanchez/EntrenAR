"""Chequeo previo a salir a producción. Uso: python manage.py check_production [--ping]"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Revisa la configuración de producción de EntrenAR (seguridad, email, IA, Hub, planes, cron)."

    def add_arguments(self, parser):
        parser.add_argument("--ping", action="store_true", help="Además probar la conexión con el Hub")

    def handle(self, *args, **o):
        self.errors = self.warnings = 0
        s = settings
        self._check(not s.DEBUG, "DEBUG está apagado", "DEBUG=1: nunca en producción")
        self._check(len(s.SECRET_KEY) >= 40 and "insecure" not in s.SECRET_KEY and "cambiar" not in s.SECRET_KEY,
                    "SECRET_KEY larga y propia", "SECRET_KEY corta o de ejemplo (generá una: "
                    "python -c 'import secrets;print(secrets.token_urlsafe(50))')")
        base = s.BASE_DOMAIN
        self._check(base not in ("localhost", "") and any(h in (f".{base}", "*") for h in s.ALLOWED_HOSTS),
                    f"ALLOWED_HOSTS cubre *.{base}", f"ALLOWED_HOSTS tiene que incluir .{base}")
        self._check(any(o_.startswith(f"https://*.{base}") for o_ in s.CSRF_TRUSTED_ORIGINS),
                    "CSRF_TRUSTED_ORIGINS con https", f"Agregá https://*.{base} y https://{base} a CSRF_TRUSTED_ORIGINS")
        self._check(s.PUBLIC_PORT_SUFFIX == "" or s.DEBUG is False, "Links sin puerto", "", warn=True)
        self._check("console" not in s.EMAIL_BACKEND and s.EMAIL_HOST, "Email SMTP configurado",
                    "Email en consola: las invitaciones y avisos no salen (EMAIL_BACKEND/EMAIL_HOST)")
        self._check("redis" in s.CACHES["default"]["BACKEND"].lower(), "Caché Redis compartida",
                    "Sin REDIS_URL: los límites de IA y el throttling se cuentan por worker", warn=True)
        self._check(bool(s.GEMINI_API_KEY), "GEMINI_API_KEY cargada", "Sin GEMINI_API_KEY: el plug-in de IA no funciona",
                    warn=True)
        self._check(bool(s.COREX_AGENT_TOKEN) and len(s.COREX_AGENT_TOKEN) >= 24, "COREX_AGENT_TOKEN (Hub → EntrenAR)",
                    "Falta COREX_AGENT_TOKEN: el Hub no puede crear ni suspender gimnasios")
        self._check(bool(s.HUB_URL and s.HUB_INGEST_TOKEN), "HUB_URL + HUB_INGEST_TOKEN (EntrenAR → Hub)",
                    "Sin HUB_URL/HUB_INGEST_TOKEN: el consumo de IA no llega al Hub para facturar")
        self._check(s.HUB_URL.startswith("https://") or not s.HUB_URL, "Hub por https", "HUB_URL debería ser https",
                    warn=True)
        self._check(s.VAPID_PUBLIC_KEY and s.VAPID_PRIVATE_KEY, "Notificaciones push (VAPID)",
                    "Sin claves VAPID: no hay notificaciones push", warn=True)
        self._check((s.PWA_DIST / "index.html").exists(), "PWA compilada", "Falta compilar la PWA (npm run build)")
        self._check((s.STATIC_ROOT).exists(), "collectstatic hecho", "Falta python manage.py collectstatic")

        from apps.tenants.models import Gym, InfraCost, SaasPlan
        self._check(Gym.objects.filter(schema_name=s.PUBLIC_SCHEMA_NAME).exists(), "Tenant público creado",
                    "Falta python manage.py setup_public")
        self._check(SaasPlan.objects.filter(is_active=True).exists(), "Planes SaaS cargados", "No hay planes activos")
        self._check(InfraCost.objects.exists(), "Costos fijos cargados (para Costos y facturación)",
                    "Cargá el VPS, backups, email… en el admin → Costos fijos", warn=True)

        if o["ping"]:
            from apps.tenants.hub_client import ping
            ok, detail = ping()
            self._check(ok, "Ping al Hub OK", f"El Hub no responde: {detail}")

        self.stdout.write("\n— check --deploy de Django —")
        try:
            call_command("check", deploy=True)
        except Exception as e:  # noqa: BLE001
            self.errors += 1
            self.stdout.write(self.style.ERROR(str(e)))
        msg = f"\n{self.errors} error(es), {self.warnings} advertencia(s)."
        self.stdout.write(self.style.ERROR(msg) if self.errors else self.style.SUCCESS(msg))
        if self.errors:
            raise SystemExit(1)

    def _check(self, cond, ok_msg, bad_msg, warn=False):
        if cond:
            self.stdout.write(self.style.SUCCESS(f"  ✔ {ok_msg}"))
        elif warn:
            self.warnings += 1
            self.stdout.write(self.style.WARNING(f"  ! {bad_msg}"))
        else:
            self.errors += 1
            self.stdout.write(self.style.ERROR(f"  ✘ {bad_msg}"))
