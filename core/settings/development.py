# core/settings/development.py
from .base import *
import dj_database_url

# SEGURIDAD EXCLUSIVA DE DESARROLLO
DEBUG = True
SECRET_KEY = config('SECRET_KEY', default='django-insecure-local-wsl-key')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,*').split(',')

# BASE DE DATOS LOCAL O EN CONTENEDOR DE DESARROLLO (Postgres)
DATABASE_URL_STR = config('DATABASE_URL', default='')
if not DATABASE_URL_STR:
    DATABASE_URL_STR = f"sqlite:////{BASE_DIR / 'db.sqlite3'}"

DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL_STR)
}
DATABASES['default']['ATOMIC_REQUESTS'] = True
DATABASES['default']['CONN_MAX_AGE'] = config('DATABASE_CONN_MAX_AGE', default=60, cast=int)
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# CORREO LOCAL (Archivos)
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'
EMAIL_TIMEOUT = 10

# Por defecto la tarea corre en el mismo proceso (sin exigir un segundo
# `manage.py qcluster` para desarrollo local). Pon Q_CLUSTER_SYNC=False en
# el .env para probar el flujo asíncrono real contra el broker ORM.
Q_CLUSTER['sync'] = config('Q_CLUSTER_SYNC', default=True, cast=bool)

#CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:8000').split(',')

# LOGS DE DESARROLLO (Salida directa y rápida a consola)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG', # Nivel detallado para encontrar bugs rápido en WSL
    },
}

# =========================================================================
# INTERRUPTOR LOCAL: Siempre encendido para inspección visual en WSL/Consola
# =========================================================================
AXENTRA_CORE_VERBOSE_RADAR = config(
    "AXENTRA_CORE_VERBOSE_RADAR",
    default=True,
    cast=bool,
)
