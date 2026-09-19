# Portal público municipal — hallazgo pendiente de resolver

Este documento registra un hallazgo real, sin implementar, encontrado al construir
los satélites `ciudadania` y `axentra-mod-tramites` (repos propios, instalados vía
`uv add --editable` en un playground desechable, nunca dentro de este repo). No
modifica código; deja el contrato por definir antes de tocar nada del Core.

## 1. Lo que ya funciona: marca blanca por instalación

`TenantConfig` (`apps/security/models/infrastructure.py`) ya resuelve identidad
visual por institución — `app_name` (valor por defecto `"GovStack"`, no
`"Axentra"`), `entidad_nombre`, `logo_light`/`logo_dark`, `primary_color`/
`secondary_color`. `templates/public/index.html` y el shell (`shell/base.html`) ya
leen estos campos vía `{{ tenant.* }}`. Cualquier instalación real solo necesita
una fila de `TenantConfig` bien llenada para que el Core deje de mostrar "Axentra"
en las superficies que ya son tenant-aware — esto no requiere código nuevo.

## 2. Resuelto en parte: "Axentra" hardcodeado fuera del alcance de TenantConfig

`grep -rn "Axentra" templates/ apps/*/templates/` (excluyendo referencias internas
de código: nombres de app, `axentra_ui`, `AxentraWorkflows`, comentarios) encontró
literales que **ningún valor de `TenantConfig` podía sobreescribir**, porque no usaban
`{{ tenant.* }}`:

- `templates/errors/403.html:67` — "Axentra OS · Control de acceso institucional".
  Página de error, visible a cualquier visitante (personal o no). **Corregido**:
  ahora `{{ tenant.app_name|default:"Axentra OS" }}` — mismo patrón que ya usaba el
  `<title>` de esa misma página. Sin tenant configurado se sigue viendo "Axentra OS".
- `templates/partials/footer.html:16` — "© 2026 Axentra Security". Alcance real
  confirmado (grep de cada `{% include %}`): solo el shell autenticado de personal
  (`shell/workbench.html` y cada `*_workbench.html`), nunca el portal público.
  **Corregido igual**: `{{ tenant.app_name|default:"Axentra OS" }}` — el resto del
  mismo footer (app_name arriba, siglas y RFC) ya leía `tenant.*`, esta era la única
  línea suelta.
- `templates/launcher/_content.html:4` — "Axentra OS" como eyebrow del launcher de
  aplicaciones (ver sección 4, launcher de personal — bajo login). **Sin tocar**,
  pedido explícito: menor prioridad, no se corrigió en esta pasada.
- Menciones adicionales, todas dentro de vistas de personal ya protegidas por login
  (`apps/security/templates/organigrama/...`, `apps/security/templates/security/...`)
  — texto de ayuda/copy interno que menciona "Axentra OS"/"Axentra Security" en
  contexto administrativo. **Sin tocar**, mismo criterio: el riesgo real era de cara
  al público, ya resuelto arriba.

Decisión de producto tomada: tenant-aware en ambos casos de cara al público, mismo
patrón que ya usaba `public/index.html` y los propios `<title>` de esas páginas —
no una atribución fija tipo "powered by Axentra".

## 3. Precisión de alcance: `/` (`public/index.html`) es la puerta de personal, no del ciudadano

Confirmado con el usuario: el Hub (`index_hub`, y su compuerta previa
`intro_portal_view` en `/`) es exclusivamente para personal — su único llamado a la
acción real es `{% url 'accounts:login' %}`, aunque su copy ("Estación Pública de
Conectividad", "Plataforma de Innovación Tecnológica") suene orientado al público
general. No confundir "tenant-aware" con "pensado para el ciudadano" — son ejes
distintos.

## 4. Lo que falta y dónde debería vivir: directorio público para el ciudadano

Existe ya un patrón real, pero solo para personal: `templates/launcher/_content.html`
+ `index_hub_view` arman un catálogo de aplicaciones instaladas (tarjetas con
nombre, ícono, descripción, estado, enlace) descubriendo satélites vía
`apps/shared/module_sdk` (`ModuleRegistry`/`ModuleManifest`, el mismo mecanismo que
ya alimenta `satellite_navigation` para el sidebar global). No existe ningún
equivalente **sin sesión**, para ciudadanos, que liste qué pueden hacer en esta
instalación (Trámites, Situaciones de Vida, su cuenta en Ciudadanía, lo que venga
después) cuando llegan al dominio principal de la institución (p. ej.
`digital.<municipio>.gob.mx`, distinto de `tramites.<municipio>.gob.mx` o
`ciudadano.<municipio>.gob.mx`, que ya tienen su propia cara pública vía
enrutamiento por dominio — ver `docs/apps/000_core_architecture.md` sección de
satélites).

Implementado (contrato aprobado):

- `ModuleManifest` (`apps/shared/module_sdk/contracts.py`) tiene el campo opcional
  `entry_url_publico: str = ""`, distinto de `entry_url` (entrada de personal en el Hub).
  Es texto plano y **nunca** pasa por `reverse()`: puede vivir en otro dominio (mismo
  criterio que `TRAMITES_PUBLIC_BASE_URL` en Situaciones de Vida). Vacío = el satélite
  no aparece en el directorio.
- `public_directory_cards()` (`apps/shared/module_sdk/services.py`) arma las tarjetas a
  partir de `module_registry.discover()`. Un módulo está habilitado si su fila `AppModule`
  está activa, o si no hay fila, según `default_enabled`. No reutiliza
  `get_module_runtime_status()`: su chequeo de salud resuelve `entry_url` (ruta de
  personal) y daría falsos negativos para una entrada pública.
- `directorio_publico_view` (`core/views.py`), ruta `/directorio/` (name
  `directorio_publico`), template `templates/public/directorio.html`. Sin login.
  **Complementa** `public/index.html` (que sigue siendo la puerta de personal); no la
  reemplaza.
- Le pertenece al Core porque agrega across satélites; ningún satélite debe conocer a los
  demás. Cada satélite solo declara su `entry_url_publico` en su `module_manifest.py`.
- El dominio público (`digital.<municipio>...`) es infraestructura, fuera de este repo.
- `descripcion_publica` (opcional, en el manifiesto): texto en lenguaje de ciudadano para
  la tarjeta; si está vacío se usa `description`, que suele estar escrita para personal.
- **Paquetes sin panel de personal** (Ciudadanía): no tienen `module_manifest.py` ni
  `AppModule`. Publican `<app>/public_entry.py` con
  `get_public_entry() -> PublicEntry | None` (`PublicEntry` en `apps.shared.module_sdk`).
  El Core lo descubre en `module_registry.public_entry_providers()` y lo llama en cada
  petición, así una setting (p. ej. `CIUDADANIA_HABILITADA`) lo apaga sin reiniciar.
  `None` o `url` vacía = no aparece. Un proveedor que falla se registra en el log y no
  tumba el directorio; si el `code` coincide con un módulo, gana el módulo. No hay
  interruptor en el Hub para estas entradas: el de cada paquete es el suyo.
- Pruebas: `apps/shared/tests/test_public_directory.py`.
