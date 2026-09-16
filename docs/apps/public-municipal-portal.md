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

## 2. Fugas reales encontradas: "Axentra" hardcodeado fuera del alcance de TenantConfig

`grep -rn "Axentra" templates/ apps/*/templates/` (excluyendo referencias internas
de código: nombres de app, `axentra_ui`, `AxentraWorkflows`, comentarios) encuentra
literales que **ningún valor de `TenantConfig` puede sobreescribir**, porque no usan
`{{ tenant.* }}`:

- `templates/errors/403.html:67` — "Axentra OS · Control de acceso institucional".
  Página de error, visible a cualquier visitante (personal o no).
- `templates/partials/footer.html:16` — "© 2026 Axentra Security". Este parcial se
  incluye ampliamente; confirmar su alcance real (¿solo shell autenticado, o también
  público?) antes de decidir el arreglo.
- `templates/launcher/_content.html:4` — "Axentra OS" como eyebrow del launcher de
  aplicaciones (ver sección 4, launcher de personal — bajo login, menor prioridad
  que las dos anteriores pero mismo defecto).
- Menciones adicionales, todas dentro de vistas de personal ya protegidas por login
  (`apps/security/templates/organigrama/...`, `apps/security/templates/security/...`)
  — texto de ayuda/copy interno que menciona "Axentra OS"/"Axentra Security" en
  contexto administrativo. Menor prioridad: el personal ya sabe qué sistema usa: el
  riesgo real es de cara al público, no aquí.

Antes de corregir: decidir si `footer.html`/`errors/*.html` deben volverse
tenant-aware (`{{ tenant.app_name|default:"GovStack" }}`, igual que
`public/index.html`) o si alguna mención de "Axentra" es aceptable a propósito
(p. ej. un pie de página que reconozca al proveedor sin ser el nombre principal
visible). No asumido aquí — es decisión de producto, no un bug de sintaxis.

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

Dirección propuesta, no implementada, requiere definir contrato antes de construir:

- Extender `ModuleManifest` (`apps/shared/module_sdk/contracts.py`) con un campo
  opcional de entrada pública (p. ej. `entry_url_publico`), distinto de `entry_url`
  (que es la entrada de personal, dentro del Hub). Un satélite sin entrada pública
  simplemente no aparece en este directorio — ciudadanía y trámites ya calificarían
  con lo que ya declaran en sus propios `module_manifest.py` (o su equivalente,
  dado que hoy viven fuera de este repo como paquetes instalables).
- Plantilla nueva del Core, análoga a `launcher/_content.html` pero pública (sin
  `@login_required`), listando solo los satélites que declaren esa entrada pública.
  No le pertenece a ningún satélite individual — ninguno debe "saber" de los demás
  — por eso vive en el Core, igual que el launcher de personal.
- Esta pieza le pertenece al Core porque agrega across satélites; ningún satélite
  debe implementarla por su cuenta.

No se decidió: nombre final de la ruta/plantilla, si reemplaza o complementa
`public/index.html` en el dominio principal, ni el contrato exacto del nuevo campo
del manifiesto. Definir antes de tocar código, mismo criterio que el resto de este
documento y de `docs/roadmap/core-hardening.md`.

## 5. Resuelto: aviso de privacidad y política de cookies, centralizados en el Core

Hallazgo relacionado, encontrado revisando `axentra-mod-tramites`: su modelo
`ConfigMunicipal` tenía su propio campo `aviso_privacidad` (texto libre) — cada
satélite instalado por separado duplicaría el mismo contenido legal si necesitara
lo mismo. No es solo desorden: es un riesgo de cumplimiento real (alguien
actualiza el aviso legal en un satélite y se le olvida en los demás).

Ya implementado en este repo (`TenantConfig`,
`apps/security/models/infrastructure.py`): dos campos nuevos,
`aviso_privacidad` y `politica_cookies`, con su propia sección en Configuración
— "Privacidad y Cookies", hermana de "Identidad Institucional" en el mismo
sidebar (`configuration_sidebar.html`), no una cuarta pestaña dentro del
formulario de identidad (que ya tiene tres: Identidad y Marca, Integraciones y
Canales, Datos Legales y Fiscales — agregar una más lo sobrecargaba). Mismo
permiso (`can_configure_tenant`, ya cubre "datos legales") y misma protección
de reautenticación (`SudoMiddleware`, automática por namespace `security`, sin
decorador aparte) que el resto de Configuración. Vista: `security:privacidad_cookies`.

**Resuelto también, fuera de este repo:** `axentra-mod-tramites` eliminó su
`ConfigMunicipal.aviso_privacidad` (pedido explícito del cliente). No hizo
falta migrar ningún portal público para leer del `TenantConfig` del Core —
revisando ese repo, el campo no llegaba a renderizarse en ningún template
(cero referencias fuera de model/form/dto/selector): estaba duplicado *y*
muerto a la vez. Se quitó sin más, sin reemplazo. Trabajo hecho en ese repo,
no en este.
