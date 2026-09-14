# AXENTRA OS — Arquitectura vigente del Core

## Plataforma municipal modular sobre Django

Este documento es la norma arquitectónica del Core de Axentra OS. Describe el
contrato que deben cumplir los componentes del núcleo y las aplicaciones
satélite. Si una implementación contradice este documento, debe corregirse la
implementación o actualizarse expresamente esta norma en el mismo cambio.

---

## 1. Objetivo

Axentra OS es un monolito modular. Comparte proceso Django, base de datos,
autenticación, sesión, shell visual y gobierno de accesos, pero mantiene los
procesos municipales en aplicaciones desacopladas.

El Core debe poder arrancar y operar:

- sin Inventory;
- con Inventory activo o desactivado;
- sin Helpdesk;
- con Helpdesk activo o desactivado;
- con cualquier combinación futura de satélites compatibles.

La ausencia de un satélite nunca debe producir un `ImportError`,
`NoReverseMatch` ni una dependencia obligatoria dentro del Core.

---

## 1.1. Límite institucional

Cada ayuntamiento opera una instalación independiente con su propia base de datos.
TenantConfig configura la identidad de esa única institución; no selecciona un
tenant dentro de una base compartida. El código puede ser común y desplegarse en
múltiples instalaciones, con sus propios secretos, volúmenes de media, logs,
caché y respaldos. No reutilizar credenciales de acceso a bases de otros municipios.

La jerarquía interna de dependencias y los permisos sobre datos se resuelven dentro
de esa instalación. La separación entre municipios es responsabilidad del despliegue,
no de un filtro por municipality_id en cada consulta. Consultar
`docs/deployment/municipal-installations.md` para el contrato operativo.

## 2. Dominios del Core

Los componentes lógicos protegidos del núcleo son:

| Código | Responsabilidad |
| --- | --- |
| `security` | Gobierno de accesos, matrices y auditoría |
| `configuration` | Identidad y parámetros institucionales |
| `accounts` | Usuarios y expedientes laborales |
| `organigrama` | Sedes, dependencias y áreas operativas |

Actualmente pueden convivir físicamente dentro de `apps.security`, pero cada
uno mantiene namespace, manifiesto de permisos y membresías independientes.

Los procesos especializados —Inventory, Helpdesk, Compras, Predial u otros—
son satélites y no deben incorporarse al código interno del Core.

---

## 3. Estructura relevante

```text
apps/
├── shared/
│   ├── module_sdk/
│   │   ├── catalog.py
│   │   ├── contracts.py
│   │   ├── integrations.py
│   │   ├── registry.py
│   │   ├── routing.py
│   │   └── services.py
│   ├── context_processors.py
│   ├── manifest_registry.py
│   └── utils/telemetry.py
│
└── security/
    ├── management/commands/
    │   ├── bootstrap_axentra_owner.py
    │   └── check_axentra_modules.py
    ├── models/
    ├── services/
    ├── templates/
    ├── views/
    ├── decorators.py
    └── permissions.py

core/
├── settings/
├── urls.py
└── views.py

templates/
├── index_hub.html
├── navigation/
└── shell/
```

---

## 4. Fuentes de verdad

| Concepto | Fuente de verdad |
| --- | --- |
| Contrato técnico de un módulo | `module_manifest.py` |
| Permisos y roles funcionales | `permissions.py` |
| Módulos instalados en el proceso | `module_registry` |
| Estado institucional activo/inactivo | `AppModule` |
| Membresía individual | `UserAppRole` |
| Permisos efectivos persistidos | `permissions_list` |
| Estructura institucional | `Sede`, `Dependencia`, `AreaOperativa` |
| Identidad del municipio | `TenantConfig` |
| Navegación global de satélites | Manifiesto + context processor |
| Navegación interna | `SIDEBAR_MENU` + gate |
| Auditoría persistente | `SecurityAuditLog` |
| Diagnóstico temporal | `AxentraRadar` + logging |

`AppIdentifier` permanece como compatibilidad para los cuatro dominios
lógicos del Core. Una aplicación satélite nueva no debe obligar a modificarlo.

---

## 5. Ciclo de vida de un módulo

Un satélite pasa por estados diferentes:

1. **Ausente:** su paquete y AppConfig no están instalados.
2. **Instalado:** Django cargó su AppConfig y el SDK descubrió su manifiesto.
3. **Desactivado:** existe, pero `AppModule.is_active=False`.
4. **Activo:** está disponible institucionalmente.
5. **Autorizado:** el usuario posee membresía y permiso fino.

La disponibilidad operativa requiere:

```text
Instalado + Activo + Usuario vigente + Membresía activa + Permiso fino
```

Desactivar un módulo:

- no elimina tablas;
- no elimina datos;
- no elimina membresías;
- no elimina permisos;
- no revierte migraciones;
- lo retira del sidebar;
- bloquea sus vistas mediante el gate.

Los módulos `CORE` tienen `can_disable=False` y no pueden apagarse desde el
Hub.

---

## 6. Contrato técnico de un satélite

Cada satélite publica `module_manifest.py`:

```python
from apps.shared.module_sdk import ModuleManifest


MODULE_MANIFEST = ModuleManifest(
    code="inventory",
    name="Inventario Patrimonial",
    description="Control de bienes y expedientes patrimoniales.",
    entry_url="inventory:dashboard",
    urlconf="apps.inventory.urls.inventory_urls",
    url_prefix="app/inventory/",
    icon="package-search",
    dependencies=("security", "accounts", "organigrama"),
    optional_integrations=("helpdesk",),
    default_enabled=False,
    can_disable=True,
)
```

Reglas:

- `code` es estable, único y en minúsculas.
- `entry_url` debe resolver cuando el satélite está instalado.
- `urlconf` sólo referencia archivos del propio satélite.
- `url_prefix` no colisiona con otras aplicaciones.
- `dependencies` contiene requisitos obligatorios.
- `optional_integrations` nunca impide arrancar el módulo.
- Ningún manifiesto importa modelos de otro satélite.

El Core descubre el archivo. No se agrega un `include()` por cada satélite en
`core/urls.py`.

---

## 7. Contrato de permisos

Cada satélite publica `permissions.py`:

```python
class InventoryPermissions:
    APP_CODE = "inventory"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo.",
        "can_view_assets": "Permite consultar bienes.",
    }

    ROLE_MAPPING = {
        "owner": ["has_access_module", "can_view_assets"],
        "viewer": ["has_access_module", "can_view_assets"],
    }

    ROLE_WEIGHTS = {
        "owner": 100,
        "viewer": 20,
    }

    SIDEBAR_MENU = [
        [
            "package-search",
            "Bienes patrimoniales",
            "inventory:asset_list",
            10,
            "can_view_assets",
        ],
    ]
```

Reglas obligatorias:

- `owner` contiene todas las llaves declaradas.
- Todo rol operativo incluye `has_access_module`.
- Ningún rol contiene llaves ausentes de `PERMISSIONS`.
- Todo elemento del sidebar referencia una llave declarada.
- Toda ruta del sidebar debe existir.
- Ocultar un botón nunca sustituye la validación backend.

`permissions_list` es el snapshot efectivo de una membresía. Las
personalizaciones explícitas de usuarios ordinarios no se sobrescriben
automáticamente al cambiar un manifiesto.

---

## 8. Gate de seguridad

Toda vista funcional usa `axentra_module_gate` o su alias compatible
`axentra_gate_enforcer`:

```python
@axentra_module_gate(
    "inventory",
    required_fine_permission="can_view_assets",
)
def asset_list_view(request):
    ...
```

Orden de validación:

1. usuario autenticado;
2. usuario `is_active=True` y `is_deleted=False`;
3. módulo instalado y activo;
4. membresía activa y no eliminada;
5. acceso general al módulo;
6. permiso fino;
7. construcción del sidebar permitido;
8. ejecución de la vista.

El estado institucional del módulo no admite bypass. Un root puede activarlo
desde el Hub, pero no operar un satélite suspendido.

El gate inyecta:

```python
request.axentra_permissions
request.axentra_permissions_list
request.axentra_is_root
request.axentra_active_module
request.axentra_sidebar_menu
```

---

## 9. Hub institucional

Ruta:

```text
/index/
```

El Hub es un panel de control, no un instalador ni un lanzador de procesos.

Responsabilidades:

- mostrar módulos detectados;
- mostrar estado activo o desactivado;
- proteger módulos Core;
- permitir al administrador global activar o desactivar satélites instalados;
- informar productos conocidos pero ausentes.

El Hub no debe:

- ejecutar `pip` o `uv`;
- modificar `INSTALLED_APPS`;
- ejecutar migraciones;
- reiniciar procesos;
- mostrar accesos operativos duplicados.

Los accesos operativos pertenecen al sidebar global.

---

## 10. Navegación dinámica

El sidebar global obtiene satélites mediante:

```text
module_registry + AppModule + UserAppRole + entry_url
```

No contiene condiciones o rutas específicas para Inventory, Helpdesk u otros
satélites.

Un enlace global aparece cuando:

- el manifiesto fue descubierto;
- el módulo está activo;
- el usuario tiene membresía activa; solo Seguridad/Configuración admiten autoridad técnica;
- `entry_url` resuelve.

El sidebar interno se genera desde `SIDEBAR_MENU` y los permisos efectivos.

---

## 11. Bootstrap del propietario

`post_migrate` sólo sincroniza metadatos de módulos. Nunca crea usuarios ni
establece contraseñas.

El propietario se aprovisiona explícitamente:

```bash
python manage.py bootstrap_axentra_owner
```

Variables requeridas:

```env
AXENTRA_OWNER_EMAIL=owner@municipio.gob.mx
AXENTRA_OWNER_DEFAULT_PASSWORD=CAMBIE_ESTA_CLAVE
```

Existe un único usuario propietario global. Ese mismo usuario recibe una
membresía `OWNER` por cada módulo instalado.

El comando es idempotente:

- no duplica usuarios;
- no duplica membresías;
- conserva la contraseña de un usuario existente;
- repara flags administrativos;
- actualiza permisos owner desde los manifiestos.

El restablecimiento explícito usa:

```bash
python manage.py bootstrap_axentra_owner --reset-password
```

---

## 12. Integraciones entre aplicaciones

Un satélite no importa modelos internos de otro satélite.

Las integraciones usan:

- contratos;
- adaptadores;
- identificadores UUID;
- snapshots cuando sea necesario;
- integraciones opcionales comprobables.

Ejemplo:

```text
Inventory ── contrato opcional ── Helpdesk
```

Inventory puede existir sin Helpdesk y Helpdesk puede existir sin Inventory.
Cuando ambos están presentes, un adaptador conecta tickets con activos sin
convertir uno en dependencia de arranque del otro.

Las relaciones con identidad y organigrama del Core pueden mantenerse mediante
adaptadores del directorio institucional.

---

## 13. Shell y HTMX

Composición oficial:

```text
shell/base.html
└── shell/workbench.html
    ├── global-sidebar
    ├── module-sidebar opcional
    └── page-content
```

Cambio de módulo:

```html
hx-target="#workbench"
hx-push-url="true"
```

Navegación interna:

```html
hx-target="#page-content"
hx-push-url="true"
```

Organización recomendada:

```text
templates/modulo/
├── pages/
├── workbench/
├── content/
├── htmx/
└── contextual/
```

Las vistas deben responder correctamente a navegación directa, `workbench`,
`page-content` y fragmentos transaccionales.

---

## 14. Capas internas de un módulo

### Models

Persistencia, restricciones e invariantes locales. No concentran flujos
completos ni navegación arbitraria hacia otras aplicaciones.

### DTO

Contratos de entrada y salida entre formularios, vistas y servicios.

### Forms

Validación de entrada y mensajes de usuario. No ejecutan transacciones de
negocio extensas.

### Selectors

Consultas exclusivamente de lectura, filtros, agregaciones y optimización.

### Services

Mutaciones, transacciones, reglas de flujo, auditoría e idempotencia.

### Views

Coordinación HTTP: parámetros, forms, selectors, services, contexto y template.

### Templates

Presentación y controles visuales. Nunca son la única barrera de autorización.

---

## 15. Baja lógica

Las consultas funcionales excluyen registros eliminados:

```python
is_deleted=False
```

Cuando se requiere disponibilidad operativa:

```python
is_active=True,
is_deleted=False,
```

Esto aplica especialmente a:

- usuarios;
- módulos;
- membresías;
- estructura organizacional;
- expedientes de negocio.

Una membresía con `is_deleted=True` nunca concede acceso aunque conserve
`is_active=True` por datos heredados.

---

## 16. Auditoría y telemetría

### Auditoría persistente

Las operaciones sensibles se registran en `SecurityAuditLog` mediante los
servicios de auditoría correspondientes.

Nunca se registran:

- contraseñas;
- tokens;
- cookies;
- encabezados de autorización;
- secretos;
- llaves privadas.

### Telemetría diagnóstica

Toda telemetría temporal usa `AxentraRadar`, nunca `print()`.

Interruptor:

```python
AXENTRA_CORE_VERBOSE_RADAR = config(
    "AXENTRA_CORE_VERBOSE_RADAR",
    default=False,
    cast=bool,
)
```

Desarrollo puede usar:

```env
AXENTRA_CORE_VERBOSE_RADAR=True
```

Producción debe usar:

```env
AXENTRA_CORE_VERBOSE_RADAR=False
```

Con el interruptor apagado no se construyen trazas diagnósticas costosas ni se
emiten registros del radar. La salida se canaliza mediante `logging` y aplica
redacción básica de campos sensibles.

---

## 17. Incorporación de un satélite

1. Incorporar su paquete y AppConfig en el proyecto de despliegue.
2. Publicar `module_manifest.py`.
3. Publicar `permissions.py`.
4. Exponer `urlconf` propio con namespace.
5. Proteger todas las vistas con el gate.
6. Crear migraciones del satélite.
7. Ejecutar:

```bash
python manage.py migrate
python manage.py check_axentra_modules --persist
python manage.py bootstrap_axentra_owner
```

8. Activarlo desde el Hub.
9. Asignar membresías a usuarios ordinarios.
10. Validar navegación directa y HTMX.

No se modifica:

- `core/urls.py` para añadir un `include()` específico;
- el sidebar global;
- el registro fijo del Core;
- los modelos internos de otra aplicación.

---

## 18. Pruebas mínimas

### Core

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py check_axentra_modules --persist
python manage.py test apps.shared.tests apps.security.tests
```

### Matriz funcional

- Core sin satélites.
- Satélite instalado y desactivado.
- Satélite instalado y activo.
- Usuario sin membresía.
- Usuario con membresía eliminada.
- Usuario inactivo o eliminado.
- Usuario sin permiso fino.
- Usuario con permiso fino.
- Owner del módulo.
- Root global.
- URL manual hacia un módulo desactivado.
- Reinicio conservando el estado institucional.

### HTMX

- Navegación directa.
- Sustitución de `#workbench`.
- Sustitución de `#page-content`.
- Historial y botón atrás.
- Respuestas con errores de formulario.
- Mensajes fuera de banda cuando corresponda.

---

## 19. Producción

Requisitos mínimos:

- `DEBUG=False`;
- `AXENTRA_CORE_VERBOSE_RADAR=False`;
- `ALLOWED_HOSTS` explícitos;
- HTTPS;
- cookies seguras;
- PostgreSQL;
- Argon2;
- secretos fuera del repositorio;
- logs persistentes y rotables;
- proxy inverso;
- servidor WSGI o ASGI de producción;
- respaldo y restauración probados.

El archivo `.env` no se versiona. Las credenciales iniciales deben rotarse antes
de la puesta en producción.

---

## 20. Regla final

Una capacidad pertenece al Core cuando es transversal:

- identidad;
- autenticación;
- permisos;
- organización;
- configuración institucional;
- auditoría;
- integración modular;
- shell compartido.

Un proceso municipal pertenece a un satélite:

- inventario;
- mesa de ayuda;
- compras;
- predial;
- catastro;
- comercio;
- obras;
- cabildo.

El Core gobierna identidad, acceso e integración. Los satélites implementan los
procesos municipales sin duplicar ni acoplar las capacidades de plataforma.

---

AXENTRA MÉXICO © 2026  
Arquitectura del Core de Axentra OS

## Gobierno de aplicaciones en Seguridad

El panel administrativo muestra un resumen de hasta cinco apps activas. El catálogo
`security:applications` permite buscar, filtrar por owner y paginar 20 registros
por página, siempre dentro del alcance del administrador global o del owner con
membresía vigente. Los conteos excluyen bajas lógicas y usuarios inactivos; miden
membresías, no autorización fina efectiva. Las agregaciones se ejecutan en SQL,
sin consultas por cada aplicación. Hub conserva activación y disponibilidad;
la matriz conserva modificación de permisos. Ambos contratos HTMX siguen vigentes.

## Alcance de datos institucionales

Regla: cada dependencia accede a sus datos; otras dependencias requieren una
autorización explícita, sin herencia jerárquica. El contrato inicial está en
`apps.shared.module_sdk.data_access` y se documenta en
[docs/apps/data-access.md](data-access.md).
El SDK requiere adopción explícita en consumidores y no cambia automáticamente
el alcance administrativo de los paneles existentes. La migración 0010 crea
las autorizaciones; aplicarla antes de utilizar este contrato.

## Autoridad técnica y reautenticación

OP#40 limita el bypass a security/configuration. Cuentas, Organigrama y satélites
requieren membresía activa y permiso fino incluso para técnicos y superusuarios.
El SDK de datos mantiene aislamiento por dependencia. Django Admin conserva el
poder del superusuario de emergencia; no es una vía operativa para dependencias.
SUDO se exige durante cinco minutos en mutaciones administrativas y no concede
permisos. Satélites adoptan sudo_required para sus operaciones sensibles, además
del gate. Contrato completo en [administrative-authority.md](administrative-authority.md).

La identidad estable es User.id (UUID), nunca el correo ni el área. UserProfile
representa adscripción laboral opcional; una futura identidad ciudadana debe tener
su propio perfil/relación y no recibir un expediente laboral ficticio. Su producto
de registro, representación y trámites ciudadanos no se implementa en OP#38–40.

## Atomicidad de auditoría — fase 4

Las escrituras HTTP en BD default se agrupan con su evidencia y sesión. Si falla
la persistencia de auditoría, la operación revierte con 503 incluso si un consumidor
captura la excepción. Servicios fuera de HTTP deben agrupar explícitamente cambio
y evidencia con transaction.atomic. No cubre archivos, correos ni otras bases.
La correlación se genera en servidor; trabajos automáticos identifican system_actor.
Snapshots usan listas explícitas de campos. Las restricciones de edición del registro
no prueban inmutabilidad frente al operador SQL. Contrato y recuperación en
[la guía operativa](../deployment/audit-continuity.md).
