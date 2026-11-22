"""
EntrenAR — SaaS multi-tenant para gimnasios (CoreX).
Un schema de PostgreSQL por gimnasio (django-tenants).
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(env(key, default)).lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = env("SECRET_KEY", "dev-insecure-change-me" if DEBUG else "")
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Falta SECRET_KEY en el .env (obligatoria con DEBUG=0).")
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", ".localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "http://*.localhost:8082,http://localhost:8082,http://*.localhost:5173").split(",") if o.strip()]

# Dominio base: cada gimnasio vive en <slug>.<BASE_DOMAIN>
BASE_DOMAIN = env("BASE_DOMAIN", "localhost")
PUBLIC_PORT_SUFFIX = env("PUBLIC_PORT_SUFFIX", ":8082")  # solo para armar links en desarrollo

# ---------------------------------------------------------------- apps
SHARED_APPS = [
    "django_tenants",
    "apps.tenants",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "corsheaders",
    "django.contrib.postgres",
    "apps.accounts",
    "apps.foods",          # catálogo de alimentos compartido entre gimnasios (schema público)
]

TENANT_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.admin",
    "apps.accounts",
    "apps.core",
    "apps.members",
    "apps.memberships",
    "apps.billing",
    "apps.classes",
    "apps.crm",
    "apps.training",
    "apps.body",
    "apps.nutrition",
    "apps.panel",
    "apps.api",
]

INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "tenants.Gym"
TENANT_DOMAIN_MODEL = "tenants.Domain"
PUBLIC_SCHEMA_NAME = "public"
SHOW_PUBLIC_IF_NO_TENANT_FOUND = False
TENANT_LIMIT_SET_CALLS = True

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenants.middleware.SubscriptionMiddleware",
]

ROOT_URLCONF = "config.urls_tenant"
PUBLIC_SCHEMA_URLCONF = "config.urls_public"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.gym",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": env("DB_NAME", "entrenar"),
        "USER": env("DB_USER", "entrenar"),
        "PASSWORD": env("DB_PASSWORD", "entrenar"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5434"),
        "CONN_MAX_AGE": 60,
    }
}
DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.FlexibleLoginBackend"]
LOGIN_URL = "panel:login"
LOGIN_REDIRECT_URL = "panel:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Build de la PWA (frontend/ -> npm run build)
PWA_DIST = BASE_DIR / "pwa_dist"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------- API
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.auth.TenantJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": None,
    "DEFAULT_THROTTLE_RATES": {"login": "20/min"},
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=60),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": True,
}
CORS_ALLOWED_ORIGIN_REGEXES = [r"^http://([a-z0-9-]+\.)?localhost:5173$"]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------- Email
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "EntrenAR <no-reply@corex.com.ar>")

# ---------------------------------------------------------------- Web Push (VAPID)
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = env("VAPID_CLAIMS_EMAIL", "mailto:soporte@corex.com.ar")

# ---------------------------------------------------------------- CoreX Hub
# ---------------------------------------------------------------- nutrición (Gemini)
GEMINI_API_KEY = env("GEMINI_API_KEY", "")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = env("GEMINI_FALLBACK_MODEL", "")  # opcional: modelo para reintentar si el principal no responde
GEMINI_TIMEOUT_S = int(env("GEMINI_TIMEOUT_S", "45"))
# "low" = respuestas en segundos. Gemini 3.8 Flash acepta low/medium/high (no "minimal"). Vacío = default del modelo (lento).
GEMINI_THINKING_LEVEL = env("GEMINI_THINKING_LEVEL", "") or "low"
if GEMINI_THINKING_LEVEL == "default":
    GEMINI_THINKING_LEVEL = ""
# Plug-in de IA: valores por defecto para gimnasios nuevos (cada gimnasio se ajusta en el admin de CoreX)
AI_PRICE_PER_1K_TOKENS = env("AI_PRICE_PER_1K_TOKENS", "8")      # ARS que CoreX cobra cada 1.000 tokens
AI_DEFAULT_MAX_DAILY = int(env("AI_DEFAULT_MAX_DAILY", "10"))    # tope diario por alumno que permite CoreX
# Solo para estimar el costo de Google y el margen en el admin
GEMINI_PRICE_INPUT_USD = env("GEMINI_PRICE_INPUT_USD", "0.75")   # USD por millón de tokens de entrada
GEMINI_PRICE_OUTPUT_USD = env("GEMINI_PRICE_OUTPUT_USD", "3.75") # USD por millón de tokens de salida
AI_FX_ARS = env("AI_FX_ARS", "1570")                             # pesos por dólar
OFF_USER_AGENT = env("OFF_USER_AGENT", "EntrenAR/1.0 (soporte@corex.com.ar)")

# Hub -> EntrenAR: token que el Hub manda en /corex/v1/ (= "API token" del servicio EntrenAR en el Hub)
COREX_AGENT_TOKEN = env("COREX_AGENT_TOKEN", "") or env("HUB_API_TOKEN", "")
HUB_SSO_SECRET = env("HUB_SSO_SECRET", "")
HUB_SSO_MAX_AGE = int(env("HUB_SSO_MAX_AGE", "60"))
# EntrenAR -> Hub: URL base del Hub y "token de ingesta" del servicio (lo muestra `corex_setup entrenar`)
HUB_URL = env("HUB_URL", "")
HUB_INGEST_TOKEN = env("HUB_INGEST_TOKEN", "")
HUB_PORTAL_URL = env("HUB_PORTAL_URL", "")

SAAS_TRIAL_DAYS = int(env("SAAS_TRIAL_DAYS", "14"))
SAAS_ALLOW_SIGNUP = env_bool("SAAS_ALLOW_SIGNUP", True)

# Invitaciones al dueño del gimnasio (link para definir la contraseña)
PASSWORD_RESET_TIMEOUT = int(env("INVITE_DAYS", "7")) * 86400

# ---------------------------------------------------------------- caché
# Producción: Redis compartido entre workers (límites de IA, throttling). Sin REDIS_URL: memoria local.
if env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL"),
                          "KEY_PREFIX": "entrenar"}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---------------------------------------------------------------- logs
LOG_DIR = env("LOG_DIR", "")
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django.security.DisallowedHost": {"handlers": [], "propagate": False}},
}
if LOG_DIR:
    LOGGING["handlers"]["file"] = {"class": "logging.handlers.RotatingFileHandler", "formatter": "std",
                                   "filename": os.path.join(LOG_DIR, "entrenar.log"),
                                   "maxBytes": 10 * 1024 * 1024, "backupCount": 10}
    LOGGING["root"]["handlers"].append("file")
ADMINS = [("CoreX", a.strip()) for a in env("ADMINS", "").split(",") if a.strip()]
if ADMINS:
    LOGGING["handlers"]["mail_admins"] = {"class": "django.utils.log.AdminEmailHandler", "level": "ERROR"}
    LOGGING["loggers"]["django.request"] = {"handlers": ["mail_admins"], "level": "ERROR", "propagate": True}
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------- seguridad (producción)
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024   # fotos de comidas
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "2592000"))  # 30 días; subir a 1 año cuando todo esté estable
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
