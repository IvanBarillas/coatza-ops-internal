# Guía técnica: crear e integrar una app satélite en Axentra OS
Ejemplo de referencia: `seguimientos_oficios`

Fuente: lectura directa de `docs/apps/000_core_architecture.md`, `apps/shared/module_sdk/*`,
`apps/security/decorators.py`, `apps/security/permissions.py`, `apps/shared/notifications/*`,
`core/settings/base.py`, `core/urls*.py`, `apps/shared/context_processors.py`,
`apps/shared/templatetags/axentra_ui.py`, `apps/security/apps.py`, `apps/shared/apps.py`,
`apps/security/models/{configuration,infrastructure}.py`, `apps/shared/checks.py`,
`apps/shared/middleware/host_urlconf.py`, `docs/deployment/satellites-real-installation.md`,
`docs/apps/data-access.md`.

---

## 1. Modelo mental: qué es un "módulo" satélite

Axentra OS es un monolito modular: un solo proceso Django, una sola BD, un solo shell.
Los procesos municipales (tu app) viven como **satélites** desacoplados del Core
(`apps/security`, `apps/shared`). El Core debe arrancar con o sin tu app instalada — nunca
debe fallar por su ausencia (`docs/apps/000_core_architecture.md:26-27`).

Ciclo de vida de un módulo (`000_core_architecture.md:125-153`):

```
Ausente → Instalado (AppConfig cargó + SDK descubrió manifest) → Desactivado
        → Activo (AppModule.is_active=True) → Autorizado (usuario con membresía + permiso fino)
```

Disponibilidad operativa real = `Instalado + Activo + Usuario vigente + Membresía activa + Permiso fino`.
Desactivar un módulo **nunca** borra tablas, datos, membresías ni permisos — solo lo oculta del
sidebar y bloquea sus vistas vía el gate.

---

## 2. Estructura de carpetas de un satélite

No hay `startapp` especial: es una app Django normal, pero **fuera** de `apps/security` y
`apps/shared` (esos son del Core). Para una instalación real vive como paquete top-level
(ej. `seguimientos_oficios/`), no dentro de `apps/`. Capas recomendadas por módulo
(`000_core_architecture.md:457-487`):

```
seguimientos_oficios/
├── apps.py                    # AppConfig
├── module_manifest.py         # contrato técnico (OBLIGATORIO para aparecer en el Hub)
├── permissions.py             # roles, llaves, sidebar (OBLIGATORIO)
├── models.py / models/
├── dtos/                       # contratos entrada/salida forms↔views↔services
├── forms/                      # validación de entrada
├── selectors/                  # solo lectura, consultas, agregaciones
├── services/                   # mutaciones, transacciones, auditoría
├── views/
├── urls.py                     # urlconf con namespace propio
├── migrations/
├── templates/seguimientos_oficios/
│   ├── pages/  workbench/  content/  htmx/  contextual/
└── tests/
```

---

## 3. El manifiesto técnico — `module_manifest.py`

Es la **fuente de verdad del contrato técnico** (`000_core_architecture.md:107`). Clase:
`ModuleManifest` en `apps/shared/module_sdk/contracts.py:24-86` — dataclass `frozen=True, slots=True`.

Campos completos (con default):

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `code` | str | sí | único, minúsculas, `[a-z0-9_-]`; no puede aparecer en sus propias `dependencies` |
| `name` | str | sí | nombre visible en el Hub |
| `description` | str | sí | texto para personal |
| `entry_url` | str | sí | nombre de ruta (`reverse()`), namespace del panel |
| `entry_url_publico` | str | "" | **texto plano**, nunca `reverse()` — entrada en `/directorio/` |
| `descripcion_publica` | str | "" | texto para el ciudadano; vacío usa `description` |
| `urlconf` | str | "" | ruta de import del urlconf del panel de personal |
| `url_prefix` | str | "" | se monta bajo `/app/...` en `core.urls` vía `satellite_urlpatterns()` |
| `version` | str | "1.0.0" | |
| `icon` | str | "blocks" | nombre de icono Lucide |
| `kind` | `ModuleKind` | `SATELLITE` | `CORE` o `SATELLITE`; tu app siempre `SATELLITE` |
| `dependencies` | tuple[str] | () | módulos obligatorios (ej. `("security","accounts","organigrama")`) |
| `optional_integrations` | tuple[str] | () | nunca bloquea el arranque |
| `default_enabled` | bool | False | estado inicial al sincronizar `AppModule` |
| `can_disable` | bool | True | los módulos CORE lo ponen en `False` |
| `api_urlconf` | str | "" | API servicio-a-servicio (django-ninja), autenticada con header `X-API-Key` = `INTERNAL_API_KEY` |
| `api_prefix` | str | "api/v1/" | se normaliza (sin `/` inicial, con `/` final); exigido si hay `api_urlconf` |
| `public_urlconf` | str | "" | urlconf de vistas públicas (sin login), se monta en `core.urls_publico` |
| `public_prefix` | str | "" | exigido si hay `public_urlconf` |

Ejemplo real de la doc (`000_core_architecture.md:160-177`), adaptado a tu app:

```python
# seguimientos_oficios/module_manifest.py
from apps.shared.module_sdk import ModuleManifest

MODULE_MANIFEST = ModuleManifest(
    code="seguimientos_oficios",
    name="Seguimiento de Oficios",
    description="Control y trazabilidad de oficios institucionales.",
    entry_url="seguimientos_oficios:dashboard",
    urlconf="seguimientos_oficios.urls",
    url_prefix="app/seguimientos-oficios/",
    icon="file-text",
    dependencies=("security", "accounts", "organigrama"),
    optional_integrations=(),
    default_enabled=False,
    can_disable=True,
)
```

**Cómo se descubre**: `ModuleRegistry.discover()` (`apps/shared/module_sdk/registry.py:58-92`)
itera `apps.get_app_configs()` e intenta importar `f"{app_config.name}.module_manifest"`; si existe
`MODULE_MANIFEST`, se registra. **No hay que llamar nada manualmente** ni tocar `core/urls.py`
— el Core nunca hace `include()` explícito por satélite (`000_core_architecture.md:205-206`,
regla reforzada en la sección 17: "No se modifica core/urls.py para añadir un include() específico").

Montaje automático de rutas: `satellite_urlpatterns()` (`apps/shared/module_sdk/routing.py:6-20`)
monta `url_prefix + urlconf` y, si existe, `api_prefix + api_urlconf`; se agrega en
`core/urls.py:28` vía `*satellite_urlpatterns()`. Análogamente `public_urlpatterns()`
(`routing.py:23-30`) se monta en `core/urls_publico.py:18` para la superficie ciudadana.

Si tu app **no** tiene panel de personal (caso no aplicable a "seguimientos de oficios", que sí
lo tiene), en vez de manifiesto publicarías `<app>/public_entry.py` con `get_public_entry()`.

---

## 4. El contrato de permisos — `permissions.py`

Clase con 4 atributos de clase obligatorios (ejemplos reales en
`apps/security/permissions.py:1-296`, plantilla en `000_core_architecture.md:214-242`):

```python
# seguimientos_oficios/permissions.py
class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"   # debe = ModuleManifest.code

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo.",
        "can_view_oficios": "Permite consultar oficios.",
        "can_create_oficio": "Permite registrar oficios nuevos.",
        "can_close_oficio": "Permite cerrar/atender un oficio.",
    }

    ROLE_MAPPING = {
        "owner": ["has_access_module", "can_view_oficios", "can_create_oficio", "can_close_oficio"],
        "editor": ["has_access_module", "can_view_oficios", "can_create_oficio"],
        "viewer": ["has_access_module", "can_view_oficios"],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20}

    SIDEBAR_MENU = [
        # [icono_lucide, texto, url_name, orden, permiso_requerido]
        ["file-text", "Oficios", "seguimientos_oficios:oficio_list", 1, "can_view_oficios"],
        ["plus-circle", "Nuevo oficio", "seguimientos_oficios:oficio_create", 2, "can_create_oficio"],
    ]
```

Reglas obligatorias (`000_core_architecture.md:244-251`):
- `owner` debe contener **todas** las llaves declaradas en `PERMISSIONS`.
- Todo rol operativo incluye `has_access_module`.
- Ningún rol referencia llaves ausentes de `PERMISSIONS`.
- Todo item de `SIDEBAR_MENU` referencia una llave declarada y una ruta que resuelve.
- **Ocultar un botón nunca sustituye la validación backend.**

**Cómo se descubre**: `AxentraOSRegistry.get_all_manifests()`
(`apps/shared/manifest_registry.py:12-67`) escanea todas las `app_config.name + ".permissions"`
instaladas, busca clases con `APP_CODE` + `PERMISSIONS`, y las indexa por `APP_CODE`. Automático,
sin registro manual — igual que el manifiesto técnico.

`permission_loader.get_app_permissions(app_slug)` (`apps/security/services/permission_loader.py`)
usa ese registro para resolver `permissions/roles/weights` de tu app cuando el admin arma la
matriz de una membresía (`UserAppRole.permissions_list`).

---

## 5. Proteger vistas — `axentra_module_gate` / `axentra_gate_enforcer`

Definido en `apps/security/decorators.py:97-211`. `axentra_gate_enforcer` es solo un alias
(`decorators.py:211`).

Firma:
```python
def axentra_module_gate(module_identifier: str, required_fine_permission: str = None):
```

Uso:
```python
from apps.security.decorators import axentra_module_gate

@axentra_module_gate("seguimientos_oficios", required_fine_permission="can_view_oficios")
def oficio_list_view(request):
    ...
```

Orden de validación exacto (`decorators.py:107-165`, resumido en `000_core_architecture.md:273-282`):
1. `request.user.is_authenticated` (si no, HTMX→403; normal→redirect a `accounts:login`).
2. Baja lógica (`is_deleted` o no `is_active`) → 403/redirect con mensaje.
3. Estado institucional del módulo vía `get_module_runtime_status()` — **no admite bypass**, ni
   siquiera root, si el módulo está `DISABLED`/`UNAVAILABLE`.
4. Acceso general (`has_access_module`), con bypass si `is_root`.
5. Permiso fino (`required_fine_permission`), con bypass si `is_root`.
6. Inyecta contexto en el `request` (ver abajo) y construye el sidebar del módulo.
7. Telemetría vía `AxentraRadar.imprimir_auditoria(...)` (no `print()`).
8. Ejecuta la vista.

Atributos inyectados en `request` que puedes usar dentro de la vista/template:
```python
request.axentra_permissions        # dict: {"has_access_module": True, "can_view_oficios": True, ...}
request.axentra_permissions_list   # list de llaves activas
request.axentra_is_root            # bool
request.axentra_active_module      # "seguimientos_oficios"
request.axentra_sidebar_menu       # sidebar ya filtrado por permiso, construido desde SIDEBAR_MENU
```

Permisos "compuestos" soportados: `"can_view_oficios"` o `"seguimientos_oficios__can_view_oficios"`
(útil si dos módulos declaran la misma llave corta).

---

## 6. Alcance de datos entre dependencias — `module_sdk.data_access`

Regla del repo: **cada dependencia ve solo sus datos**; sin herencia jerárquica, ni por
`Dependencia.parent`, puesto, sede o rol admin (`docs/apps/data-access.md:1-5`). Módulo:
`apps/shared/module_sdk/data_access.py`.

Dos funciones:

```python
def authorized_departments(user, *, app_slug, permission):
    """Devuelve un QuerySet de Dependencia visibles: la propia + excepciones vigentes
    en DepartmentAccessGrant. Exige: usuario activo, módulo disponible, membresía activa,
    permiso declarado y vigente, perfil laboral activo con área/dependencia activas."""

def scope_queryset(queryset, user, *, app_slug, permission, department_field='dependencia'):
    """queryset.filter(**{f'{department_field}__in': authorized_departments(...)})"""
```

Uso típico en un selector/vista de tu app (ejemplo real de la doc,
`docs/apps/data-access.md:11-24`):

```python
from django.shortcuts import get_object_or_404
from apps.shared.module_sdk.data_access import scope_queryset

visible = scope_queryset(
    Oficio.objects.filter(is_deleted=False),
    request.user,
    app_slug="seguimientos_oficios",
    permission="can_view_oficios",
    department_field="dependencia",   # nombre de campo FK en TU modelo hacia Dependencia
)
oficio = get_object_or_404(visible, pk=pk)
```

Puntos clave que el equipo insiste en repetir:
- `app_slug`/`permission` son **constantes del código**, nunca vienen de query params.
- No sustituye tu gate funcional (`axentra_module_gate`); es un filtro adicional de fila.
- Para altas/cambios de adscripción valida también el destino con `authorized_departments(...)`
  dentro de la misma transacción.
- Requiere la migración `0010_department_access_grants` aplicada (ya está en `apps/security`).
- No hay adopción automática: si tu app no llama esto, no hay aislamiento por dependencia.

---

## 7. Correo — siempre vía `enqueue_email()`, nunca `EmailMessage`/`send_mail`

`apps/shared/notifications/services.py:18-38`:

```python
def enqueue_email(*, subject, body, to, from_email=None, ascii_only=True):
    """to: email o lista. Encola con transaction.on_commit() — si la transacción
    actual revierte, el correo nunca se encola. Django-Q2, broker ORM (sin Redis)."""
```

Uso real en el repo (`apps/security/views/identity_views.py:61,123,128`,
`apps/security/models/accounts.py:86`):

```python
from apps.shared.notifications.services import enqueue_email

enqueue_email(
    subject="Confirma tu nuevo correo de acceso",
    body=mensaje_texto_plano,
    to=usuario.pending_email,
)
```

Reglas de `AGENTS.md` reforzadas por el código:
- **Nunca** construir `EmailMessage`/`send_mail` fuera de este módulo.
- No llamar `send_email_task` a mano — `enqueue_email` ya usa `transaction.on_commit`.
- En tests que dependan del correo: `self.captureOnCommitCallbacks(execute=True)`
  (si no, `on_commit` nunca dispara porque `TestCase` revierte su transacción).
- `Q_CLUSTER['sync']` (vía `Q_CLUSTER_SYNC` en dev, default `True`) corre la tarea en el mismo
  proceso al hacer commit — no necesitas `manage.py qcluster` en desarrollo.

---

## 8. `INSTALLED_APPS` — cómo se registra tu app (sin tocar `core/settings/base.py`)

`core/settings/base.py:58-73`:

```python
LOCAL_APPS = [
    'apps.shared.apps.SharedConfig',
    'apps.security.apps.SecurityConfig',
]

# Satélites por entorno, vía .env — CSV: "django_quill,seguimientos_oficios"
AXENTRA_EXTRA_APPS = _csv_env('AXENTRA_EXTRA_APPS')

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS + [
    app for app in AXENTRA_EXTRA_APPS
    if app not in DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
]
```

Es decir: **no editas `base.py`**. Instalas tu app agregando su nombre (o `apps.py:AppConfig`
dotted path) a la variable de entorno `AXENTRA_EXTRA_APPS` en tu `.env.<DJANGO_ENV>`:

```env
AXENTRA_EXTRA_APPS=seguimientos_oficios
```

Otras settings relevantes ya provistas por el Core que tu app puede/debe usar directamente
(no las redefinas):
- `AUTH_USER_MODEL = 'security.User'`
- `LOGIN_URL = 'accounts:login'`, `LOGIN_REDIRECT_URL = 'index_hub'`
- `TEMPLATES[0]['OPTIONS']['context_processors']` ya incluye los 4 context processors del Core
  (sección 9) — se aplican automáticamente a los templates de tu app, no necesitas agregarlos.
- `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` (pero usa `AxentraBaseModel`, ver §12).
- `Q_CLUSTER` ya configurado — no crees tu propia cola.
- `AXENTRA_CORE_VERBOSE_RADAR` — usa `AxentraRadar` (`apps.shared.utils.telemetry`) para
  telemetría de diagnóstico, nunca `print()`.
- `INTERNAL_API_KEY` — si publicas `api_urlconf`, valida el header `X-API-Key` contra esto.
- `AXENTRA_HOST_URLCONFS` — solo relevante si tu app también publica `public_urlconf`
  (superficie ciudadana); ver §10.
- `<NOMBRE>_PUBLIC_BASE_URL` — patrón de settings dinámicas: cualquier variable de entorno que
  matchee `^[A-Z][A-Z0-9_]*_PUBLIC_BASE_URL$` se expone automáticamente como setting
  (`base.py:278-280`). Ej.: `SEGUIMIENTOS_OFICIOS_PUBLIC_BASE_URL` si tu app tuviera vistas en
  otro dominio ciudadano.

---

## 9. Templates: context processors y templatetags disponibles

Los 4 context processors (`core/settings/base.py:126-129`, implementados en
`apps/shared/context_processors.py`) están activos globalmente — tu app los recibe gratis:

| Context processor | Qué inyecta |
|---|---|
| `global_tenant_settings` | `{{ tenant }}` (instancia `TenantConfig`: branding, logo, colores) y `{{ admin_panel_path }}` |
| `user_module_permissions` | `{{ allowed_modules }}` (slugs de módulos con membresía activa), `{{ is_global_admin }}` |
| `satellite_navigation` | `{{ satellite_navigation }}`: lista de dicts `{code,name,icon,url}` de satélites que el usuario puede abrir — **tu módulo aparece aquí automáticamente** si `kind=SATELLITE` y el usuario tiene acceso; no hay condicional hardcodeado por satélite |
| `menu_dinamico_processor` | `{{ menu_actual }}`/`{{ sidebar_menu }}` (tu `SIDEBAR_MENU` ya filtrado por permiso), `{{ operator_identity }}`, `{{ modulo_actual }}` |

`menu_dinamico_processor` (`context_processors.py:253-314`) prioriza
`request.axentra_sidebar_menu` (ya inyectado por el gate) sobre reconstruirlo desde el
manifiesto — si usas el decorador correctamente no necesitas hacer nada extra.

Templatetags de `apps/shared/templatetags/axentra_ui.py` (cárgalos con
`{% load axentra_ui %}`), útiles para tu app:
- `{% stats_card label value icon ... %}` — tarjeta contadora reusable.
- `{% define_url_context boton request %}`, `define_button_icon`, `define_button_text`,
  `define_button_permission`, `define_button_order` — resuelven items de `SIDEBAR_MENU` sea
  lista/tupla o dict.
- `{{ mi_diccionario|get_item:mi_llave }}` — filtro para leer dicts en templates.
- `{% confirm_modal %}`, `{% badge_toggle is_active toggle_url %}`, `{% user_search_filter ... %}`
  — componentes HTMX reusables.

---

## 10. Shell y contrato HTMX

Composición oficial (`000_core_architecture.md:415-453`):
```
shell/base.html → shell/workbench.html → #global-sidebar, #module-sidebar (opcional), #page-content
```

- Cambiar de módulo: `hx-target="#workbench"` `hx-push-url="true"`.
- Navegación interna del módulo: `hx-target="#page-content"` `hx-push-url="true"`.
- Toda vista debe responder correctamente a: navegación directa, swap de `#workbench`, swap de
  `#page-content`, historial/atrás, mensajes fuera de banda (OOB) cuando aplique.
- Organiza tus templates en `pages/ workbench/ content/ htmx/ contextual/` dentro de
  `templates/seguimientos_oficios/`.

---

## 11. Superficie pública (ciudadano) — opcional

Solo si tu app necesita vistas sin login para el ciudadano. Dos dominios distintos
(`docs/deployment/satellites-real-installation.md:6-17`):

| Cara | Urlconf | Contenido |
|---|---|---|
| Personal | `core.urls` (`ROOT_URLCONF`) | Hub, `/directorio/`, `/app/...`, API interna |
| Ciudadano | `core.urls_publico` | `/`, y cada satélite bajo su `public_prefix` |

Declaras en el manifiesto: `public_urlconf="seguimientos_oficios.urls_publico"`,
`public_prefix="oficios/"`. Se monta automáticamente vía `public_urlpatterns()`
(§3). El host que sirve el dominio ciudadano se configura en `.env`:
```env
AXENTRA_HOST_URLCONFS=ciudadano.tu-municipio.mx=core.urls_publico
```
(`HostUrlconfMiddleware`, primero en `MIDDLEWARE`, fija `request.urlconf` según el host —
sin esta variable el middleware es no-op). Un solo dominio ciudadano = una sola cookie de
sesión para todos los satélites públicos; **nunca** repartas vistas públicas de un mismo
producto entre varios dominios.

Comprobaciones de arranque que esto puede disparar (`apps/shared/checks.py`, `manage.py check`):
- `axentra.E001` — el urlconf de `AXENTRA_HOST_URLCONFS` no importa.
- `axentra.E002` — ese módulo no define `urlpatterns`.
- `axentra.E003` — dos paquetes comparten el mismo `public_prefix`.
- `axentra.W001` — el host no está en `ALLOWED_HOSTS`.
- `axentra.W002` — hay módulos con `api_urlconf` pero `INTERNAL_API_KEY` vacía.

---

## 12. Modelos: hereda `AxentraBaseModel`

`apps/shared/models.py:6-36` — abstracto, dale herencia a **todos** tus modelos de negocio:

```python
class AxentraBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def soft_delete(self, save=True): ...   # is_active=False, is_deleted=True, deleted_at=now()
    def restore(self, save=True): ...
```

Regla de baja lógica (`000_core_architecture.md:491-515`): toda consulta funcional filtra
`is_deleted=False`; cuando importa disponibilidad operativa, `is_active=True, is_deleted=False`.

Identidad de usuario estable: **`User.id` (UUID)**, nunca el correo — `000_core_architecture.md:718-719`.

---

## 13. Auditoría y telemetría

- Operaciones sensibles → `SecurityAuditLog` (`apps.security.models.audit`) vía los servicios
  de auditoría del Core. Nunca registrar contraseñas, tokens, cookies, headers de auth, secretos.
- Diagnóstico temporal en desarrollo → `AxentraRadar` (`apps.shared.utils.telemetry`), nunca
  `print()`. Interruptor: `AXENTRA_CORE_VERBOSE_RADAR` (bool, `.env`).
- `AuditTransactionMiddleware` (antes de `SessionMiddleware`) agrupa escrituras HTTP en la BD
  default y revierte con 503 si falla la auditoría — aplica también a tus vistas sin que hagas
  nada, pero si tienes lógica fuera del ciclo HTTP (management command, tarea Django-Q2) debes
  envolver cambio + evidencia en `transaction.atomic` tú mismo.

---

## 14. Los `AppConfig` del Core — patrón a replicar

`apps/security/apps.py:23-38` conecta `post_migrate` para sincronizar metadatos de módulos
(`sync_installed_modules()`, §15) — **nunca crea usuarios**. `apps/shared/apps.py:7-21` descubre
automáticamente `workflows/` y registra `apps/shared/checks.py`.

Tu `AppConfig` normalmente no necesita hacer nada especial — Django ya descubre
`module_manifest.py`/`permissions.py` por convención de nombre de módulo, sin `ready()` custom.
Solo agrega lógica en `ready()` si necesitas registrar signals propios de tu app.

```python
# seguimientos_oficios/apps.py
from django.apps import AppConfig

class SeguimientosOficiosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "seguimientos_oficios"
    verbose_name = "Seguimiento de Oficios"
```

---

## 15. Los modelos que registran tu módulo (no los tocas directo, pero debes conocerlos)

`apps/security/models/infrastructure.py`:

- **`AppModule`** (línea 15+): inventario institucional. Campos clave: `slug` (único, = tu
  `code`), `is_active`, `is_deleted`, `module_kind` (`CORE`/`SATELLITE`), `dependencies` (JSON),
  `health_status`/`health_message`/`last_health_check_at`, `entry_url_name`.
- **`UserAppRole`** (línea 56+): membresía individual. FK `user`→`AUTH_USER_MODEL`, FK
  `app`→`AppModule`, `role` (string libre definido en tu `ROLE_MAPPING`), y (heredado de
  `AxentraBaseModel`) `is_active`/`is_deleted`. El snapshot efectivo de permisos vive en
  `permissions_list` (campo JSON, no sobrescrito automáticamente al cambiar tu manifiesto —
  `000_core_architecture.md:253-255`).
- **`TenantConfig`**: identidad institucional (branding); inyectada por `global_tenant_settings`.

**Quién sincroniza `AppModule` desde tu manifiesto**: `sync_installed_modules()`
(`apps/shared/module_sdk/services.py:19-57`), invocada por `post_migrate` (dev) y por el comando
`check_axentra_modules --persist` (producción/CI). `get_or_create` por `slug`; en actualizaciones
nunca reactiva un módulo que un admin desactivó manualmente (`is_active` se excluye de los campos
sincronizados salvo para módulos `can_disable=False`, que siempre se fuerzan a `True`).

---

## 16. Flujo operativo completo — de código a módulo activo

(`000_core_architecture.md:567-586`, sección "Incorporación de un satélite")

1. Agregar tu paquete a `AXENTRA_EXTRA_APPS` en el `.env` del entorno (nunca editar
   `core/settings/base.py`).
2. Publicar `module_manifest.py` (§3).
3. Publicar `permissions.py` (§4).
4. Exponer tu `urlconf` con namespace propio (`app_name = "seguimientos_oficios"` en tu `urls.py`).
5. Proteger **todas** las vistas con `axentra_module_gate` (§5).
6. Crear tus migraciones (`manage.py makemigrations seguimientos_oficios`).
7. Ejecutar:
   ```bash
   python manage.py migrate
   python manage.py check_axentra_modules --persist
   python manage.py bootstrap_axentra_owner
   ```
8. Activar el módulo desde el Hub (`/index/`) — un admin global (`is_platform_admin`).
9. Asignar membresías (`UserAppRole`) a usuarios ordinarios vía el panel de Seguridad.
10. Validar navegación directa y comportamiento HTMX (`#workbench`, `#page-content`, historial).

**Nunca modificar**: `core/urls.py` para añadir un `include()` de tu app, el sidebar global
(código), el registro fijo del Core, ni modelos internos de otra app satélite/del Core.

---

## 17. Checklist de verificación local (antes de dar por terminado)

```bash
DJANGO_ENV=build uv run python manage.py check
DJANGO_ENV=build uv run python manage.py makemigrations --check --dry-run
DJANGO_ENV=build uv run python manage.py check_axentra_modules --persist
DJANGO_ENV=build uv run python manage.py test apps.shared.tests apps.security.tests
```

Matriz funcional mínima (`000_core_architecture.md:608-621`): Core sin tu satélite; satélite
instalado+desactivado; instalado+activo; usuario sin membresía; membresía eliminada; usuario
inactivo/eliminado; usuario sin permiso fino; usuario con permiso fino; owner del módulo; root
global; acceso manual a URL de módulo desactivado; reinicio conservando estado institucional.

---

## Resumen ejecutivo (los 5 archivos que SIEMPRE debes escribir)

| Archivo | Obligatorio | Propósito |
|---|---|---|
| `module_manifest.py` con `MODULE_MANIFEST` | Sí | te hace aparecer en el Hub y monta tus rutas |
| `permissions.py` con clase `APP_CODE`+`PERMISSIONS`+`ROLE_MAPPING`+`ROLE_WEIGHTS`+`SIDEBAR_MENU` | Sí | define roles, llaves finas y menú lateral |
| `urls.py` con `app_name` propio | Sí | namespace de tus vistas |
| Vistas decoradas con `@axentra_module_gate("tu_code", required_fine_permission="...")` | Sí | única barrera de autorización real |
| `apps.py` con `AppConfig` simple | Sí (Django lo exige) | nombre de la app en `INSTALLED_APPS` |

Todo lo demás (sidebar, navegación global, launcher, matriz de permisos en el panel de
Seguridad, sincronización de `AppModule`) es automático una vez estos 5 existen — el Core
descubre por convención de nombre de módulo, no por registro manual.
