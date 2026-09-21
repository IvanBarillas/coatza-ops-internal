# Satélites en una instalación real

Hasta ahora las vistas públicas y la API de un satélite solo se montaban a mano en un playground. Este contrato lo
resuelve sin que el Core conozca a ningún satélite y sin romper una instalación que no lo use: todo es opcional.

## Dos caras, dos dominios

| Cara | Dominio (ejemplo) | Urlconf | Contenido |
|---|---|---|---|
| Personal | `digital.<municipio>` | `ROOT_URLCONF` (`core.urls`) | Hub, `/directorio/`, `/app/...` (dashboards), API interna |
| Ciudadano | `ciudadano.<municipio>` | `core.urls_publico` | directorio en `/`, y cada satélite bajo su prefijo (`/tramites/`, `/situaciones/`, `/ciudadano/`) |

**Por qué un solo dominio ciudadano.** Ciudadanía guarda su sesión en `request.session` (cookie por host) y Trámites y
Situaciones dependen de ella (iniciar una solicitud, seguir una guía, saludar por nombre). Con un dominio por satélite la sesión
no se comparte y `reverse('ciudadania:login')` no resuelve fuera de su urlconf. Compartir la cookie con `SESSION_COOKIE_DOMAIN`
mezclaría la sesión del personal con la ciudadana. Separar personal y ciudadano también evita el choque de `app_name` entre el
panel y el portal público de un mismo satélite (nunca comparten urlconf).

## Lo que declara un satélite

En `module_manifest.py` (todo opcional):

```python
ModuleManifest(
    ...,
    urlconf="portal.urls_dashboard", url_prefix="app/tramites/",      # panel de personal (ya existía)
    api_urlconf="portal.urls_api", api_prefix="api/v1/",              # API servicio-a-servicio (X-API-Key = INTERNAL_API_KEY)
    public_urlconf="portal.urls_publico", public_prefix="tramites/",  # vistas públicas -> core.urls_publico
)
```

Un paquete sin panel (Ciudadanía) declara `PUBLIC_URLCONF` y `PUBLIC_PREFIX` como constantes en `<app>/public_entry.py`.
`ModuleManifest` normaliza los prefijos (`api/v1/`, sin `/` inicial) y exige un prefijo si hay urlconf.

## Lo que configura la instalación (entorno)

| Variable | Efecto | Por defecto |
|---|---|---|
| `AXENTRA_EXTRA_APPS` | apps (satélites y sus dependencias) que se añaden a `INSTALLED_APPS`, separadas por coma | vacío |
| `AXENTRA_HOST_URLCONFS` | `host=urlconf[,host=urlconf]`; el host elige el urlconf (p. ej. `ciudadano.example.mx=core.urls_publico`). Formato inválido: falla al arrancar | vacío (middleware inactivo) |
| `INTERNAL_API_KEY` | llave de la API de los satélites; vacía = no autentica a nadie | vacía |
| `<NOMBRE>_PUBLIC_BASE_URL` | URL base pública de cada satélite (enlaces entre dominios, nunca `reverse()`); con prefijo si el satélite va bajo uno (`https://ciudadano.example.mx/tramites`) | sin definir (la tarjeta no aparece) |
| `SECURE_REDIRECT_EXEMPT` (producción) | regex de rutas exentas de la redirección a HTTPS, p. ej. `^api/v1/` para que un servicio interno llame por http | vacío |

`ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` deben incluir cada dominio (y el nombre interno con el que un servicio llama a la API).

## Comprobaciones de arranque (`manage.py check`)

`axentra.E001` (urlconf de `AXENTRA_HOST_URLCONFS` no importable), `E002` (sin `urlpatterns`), `E003` (dos paquetes con el mismo
prefijo público), `W001` (host fuera de `ALLOWED_HOSTS`), `W002` (módulos con API e `INTERNAL_API_KEY` vacía).

## Compatibilidad

Los campos nuevos de `ModuleManifest` son opcionales: un satélite viejo sigue funcionando en un Core nuevo. Al revés no: un
satélite que declare `api_urlconf`/`public_urlconf` falla en un Core anterior; actualizar el Core primero.

## Despliegue

`deploy/podman-ops/` (Containerfile, `build.sh`, units Quadlet, script de paridad y RUNBOOK) para el entorno semi real DEV.
