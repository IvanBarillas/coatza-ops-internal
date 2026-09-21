# core/settings/production.py
from .base import *
from .base import _csv_env
import dj_database_url

# SEGURIDAD INMUTABLE DE PRODUCCIÓN (Obligatorio desde .env.prod)
DEBUG = False
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS').split(',')

# BASE DE DATOS DE PRODUCCIÓN
DATABASE_URL_STR = config('DATABASE_URL')
DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL_STR)
}
DATABASES['default']['ATOMIC_REQUESTS'] = True
DATABASES['default']['CONN_MAX_AGE'] = config('DATABASE_CONN_MAX_AGE', default=60, cast=int)
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# CORREO DE PRODUCCIÓN (SMTP)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
# Sin esto Django no acota la espera por un SMTP colgado: el valor por
# defecto es None (sin límite), y un socket que nunca responde bloquea
# indefinidamente el worker de la cola (o, antes de esta migración, el
# propio request). El worker de Django-Q2 ya reintenta solo, así que un
# timeout corto aquí es preferible a esperar de más.
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)

# La cola siempre es asíncrona real en producción: el broker ORM (ver
# Q_CLUSTER en base.py) la ejecuta un proceso `manage.py qcluster` aparte,
# nunca el propio request.
Q_CLUSTER['sync'] = False

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Cookies y Blindaje SSL
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
# Rutas que NO se redirigen a HTTPS (expresiones regulares sobre la ruta sin "/"
# inicial). Vacío por defecto. Sirve para que un servicio del mismo host llame
# a la API por http interno (p. ej. ``^api/v1/``) mientras el proxy sigue
# redirigiendo todo lo externo.
SECURE_REDIRECT_EXEMPT = _csv_env('SECURE_REDIRECT_EXEMPT')
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if origin.strip()
]

# LOGS DE PRODUCCIÓN (Estructurados, persistidos en archivos para auditorías)
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'production_django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'WARNING', 
    },
}

# =========================================================================
# VELOCIDAD CERO: Apagado estricto e inmutable para entorno en vivo
# =========================================================================
AXENTRA_CORE_VERBOSE_RADAR = config(
    "AXENTRA_CORE_VERBOSE_RADAR",
    default=False,
    cast=bool,
)
