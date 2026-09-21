
# core/settings/base.py
from pathlib import Path
from decouple import Config, RepositoryEmpty, RepositoryEnv
import os
import re
import warnings

from django.core.exceptions import ImproperlyConfigured

# =========================================================
# CARGA DE ENTORNO EN RAÍZ
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV = os.getenv("DJANGO_ENV", "dev")
ENV_FILE = BASE_DIR / f".env.{ENV}"

ENV_FILE_EXISTS = ENV_FILE.exists()
if not ENV_FILE_EXISTS:
    warnings.warn(
        f"No se encontro el archivo de entorno '{ENV_FILE.name}' en {BASE_DIR}. "
        "Se continua con una configuracion vacia (RepositoryEmpty); las "
        "variables sin valor por defecto fallaran explicitamente al resolverse.",
        RuntimeWarning,
        stacklevel=2,
    )

repository = RepositoryEnv(str(ENV_FILE)) if ENV_FILE_EXISTS else RepositoryEmpty()
config = Config(repository)

def _csv_env(name):
    """Lista separada por comas de una variable de entorno (vacía si no existe)."""
    return [item.strip() for item in config(name, default='').split(',') if item.strip()]


# =========================================================
# APPLICATIONS (Estructura fija)
# =========================================================
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'axes',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'django_q',

]

LOCAL_APPS = [
    'apps.shared.apps.SharedConfig',
    'apps.security.apps.SecurityConfig',
]

# Satélites y sus dependencias propias que esta instalación incorpora, por
# entorno (p. ej. ``django_quill,portal.apps.PortalConfig,ciudadania``), sin
# editar este archivo. Vacío por defecto: el Core arranca sin satélites. Cada
# entrada debe ser instalable en la imagen; una que no lo sea es un error de
# configuración y Django falla al arrancar.
AXENTRA_EXTRA_APPS = _csv_env('AXENTRA_EXTRA_APPS')

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + [
    app for app in AXENTRA_EXTRA_APPS
    if app not in DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
]

# =========================================================
# MIDDLEWARE (Estructura fija)
# =========================================================
MIDDLEWARE = [
    # Primero: fija request.urlconf según el host (no-op sin AXENTRA_HOST_URLCONFS).
    'apps.shared.middleware.host_urlconf.HostUrlconfMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'apps.security.middleware.audit.AuditTransactionMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'apps.security.middleware.sessions.AccountSessionMiddleware',
    'apps.security.middleware.identity.IdentityLifecycleMiddleware',
    'apps.security.middleware.sudo.SudoMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'

# =========================================================================
# RUTA OFUSCADA DEL PANEL DE ADMINISTRACIÓN
# =========================================================================
# Fuente única de verdad para core/urls.py; evita instanciar un segundo
# Config de decouple fuera de este archivo.
ADMIN_SECRET_PATH = config(
    "ADMIN_SECRET_PATH",
    default="axentra-core-secret-portal-manager-wsl/",
)

# =========================================================
# TEMPLATES (Estructura fija)
# =========================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                
                # LOS INYECTORES DE GOBERNANZA GLOBAL DE AXENTRA OS
                'apps.shared.context_processors.global_tenant_settings',    # Activos de marca e identidad ({{ tenant }})
                'apps.shared.context_processors.user_module_permissions',  # Lista de apps asignadas ({{ allowed_modules }})
                "apps.shared.context_processors.satellite_navigation",
                'apps.shared.context_processors.menu_dinamico_processor',
            ],
        },
    },
]

# =========================================================
# CONFIGURACIONES INTERNAS FIJAS
# =========================================================
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# =========================================================================
# CONFIGURACIÓN DE AUTENTICACIÓN Y REDIRECCIÓN CORE
# =========================================================================
# Destino definitivo tras un login exitoso (Apunta a tu path('launcher/', ...))
LOGIN_REDIRECT_URL = 'index_hub'

# Destino en caso de que un usuario intente entrar a una ruta protegida sin sesión
LOGIN_URL = 'accounts:login'

# Destino tras cerrar sesión en el sistema
LOGOUT_REDIRECT_URL = '/'

AUTH_USER_MODEL = 'security.User'

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_RESET_ON_SUCCESS = True
AXES_LOCK_OUT_BY_COMBINATION = True

LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="webmaster@localhost")

# =========================================================================
# CACHÉ (LocMemCache por defecto; Redis si CACHE_BACKEND=redis)
# =========================================================================
CACHE_BACKEND = config("CACHE_BACKEND", default="locmem")

if CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "axentra-core-locmem",
        }
    }

# =========================================================================
# COLA DE TAREAS ASÍNCRONAS (Django-Q2, broker ORM — sin Redis/RabbitMQ)
# =========================================================================
# El broker 'orm' usa las tablas propias de django_q en la misma base de
# datos que ya está corriendo (SQLite en dev, Postgres en prod); no suma un
# servicio de infraestructura nuevo, igual que la decisión de LocMemCache
# sobre Redis para el caché. 'sync' se sobreescribe por entorno: en
# desarrollo corre en el mismo proceso por defecto (sin exigir un segundo
# `manage.py qcluster` corriendo), en producción siempre es asíncrono real.
Q_CLUSTER = {
    'name': 'axentra_core',
    'orm': 'default',
    'workers': config('Q_CLUSTER_WORKERS', default=2, cast=int),
    'timeout': 30,
    'retry': 90,
    'max_attempts': 3,
    'catch_up': False,
    'ack_failures': True,
}

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# =========================================================================
# CONFIGURACIÓN SOBERANA DE TELEMETRÍA (AXENTRA RADAR INTERRUPTOR)
# =========================================================================
# Lee del archivo .env correspondiente; si no existe, por defecto se apaga.
AXENTRA_CORE_VERBOSE_RADAR = config('AXENTRA_CORE_VERBOSE_RADAR', default=False, cast=bool)

# =========================================================================
# SUPERFICIES DE LOS SATÉLITES EN UNA INSTALACIÓN REAL (todo por entorno)
# =========================================================================
# Host -> urlconf. ``AXENTRA_HOST_URLCONFS=ciudadano.example.mx=core.urls_publico``
# (varios separados por coma). Ver apps/shared/middleware/host_urlconf.py.
def _parse_host_urlconfs(raw):
    mapping = {}
    for item in [part.strip() for part in raw.split(',') if part.strip()]:
        host, sep, urlconf = item.partition('=')
        host, urlconf = host.strip().lower(), urlconf.strip()
        if not sep or not host or not urlconf:
            raise ImproperlyConfigured(
                f"AXENTRA_HOST_URLCONFS: entrada inválida {item!r}; "
                "el formato es host=paquete.urlconf[,host=paquete.urlconf]."
            )
        mapping[host] = urlconf
    return mapping


AXENTRA_HOST_URLCONFS = _parse_host_urlconfs(config('AXENTRA_HOST_URLCONFS', default=''))

# Llave de la API servicio-a-servicio de los satélites (cabecera X-API-Key).
# Vacía = la API no autentica a nadie; en producción se inyecta como secreto.
INTERNAL_API_KEY = config('INTERNAL_API_KEY', default='')

# URL base pública de cada satélite (``<NOMBRE>_PUBLIC_BASE_URL``): enlaces entre
# dominios, nunca reverse(). El Core no conoce a los satélites: expone como
# setting cualquier variable con ese sufijo. Sin ellas, la tarjeta del
# directorio público no aparece.
for _name in sorted(set(os.environ) | set(getattr(repository, 'data', {}))):
    if re.fullmatch(r'[A-Z][A-Z0-9_]*_PUBLIC_BASE_URL', _name):
        globals()[_name] = config(_name, default='')

# =========================================================
# APROVISIONAMIENTO DEL OPERADOR INICIAL
# =========================================================

AXENTRA_OWNER_EMAIL = config(
    "AXENTRA_OWNER_EMAIL",
    default="owner@axentra.com.mx",
)

AXENTRA_OWNER_DEFAULT_PASSWORD = config(
    "AXENTRA_OWNER_DEFAULT_PASSWORD",
    default="",
)

# MFA obligatorio para cuentas administrativas; otros usuarios pueden inscribirse.
AXENTRA_REQUIRE_ADMIN_MFA = config('AXENTRA_REQUIRE_ADMIN_MFA', default=True, cast=bool)
OTP_TOTP_ISSUER = config('OTP_TOTP_ISSUER', default='Axentra OS')
OTP_TOTP_THROTTLE_FACTOR = 1
OTP_STATIC_THROTTLE_FACTOR = 1
AXENTRA_REQUIRE_VERIFIED_EMAIL = config('AXENTRA_REQUIRE_VERIFIED_EMAIL', default=True, cast=bool)
