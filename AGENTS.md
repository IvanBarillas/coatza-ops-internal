# Contexto de Axentra Core Django

## Propósito y arquitectura

Axentra OS es un monolito modular para plataformas municipales. Comparte Django,
base de datos, autenticación, sesión, permisos, auditoría y shell visual. Los
procesos especializados pertenecen a satélites opcionales. Cada ayuntamiento tiene
su propia instalación y base de datos; no introducir multi-tenancy compartido.
Archivos, secretos, caché y respaldos también deben estar separados por instancia. Leer
`docs/apps/000_core_architecture.md` antes de cambiar contratos del Core; es la
norma arquitectónica y contiene los detalles de permisos, navegación y módulos.

Stack: Python >=3.13, Django 6, dependencias y resolución en `pyproject.toml` y
`uv.lock`; PostgreSQL en contenedores, SQLite por defecto local; plantillas Django,
HTMX, Alpine, Lucide, Chart.js, Mermaid y Tailwind 4 standalone. WhiteNoise sirve
estáticos compilados y Argon2/axes forman parte de autenticación y protección.

## Mapa del repositorio

- `core/settings/base.py`: configuración común, entorno `.env.<DJANGO_ENV>`,
  apps, middleware, usuario personalizado, caché y estáticos.
- `core/settings/development.py`, `production.py`: ajustes por entorno.
  `manage.py` usa development por defecto; verificar el módulo de settings en
  comandos de producción. No leer ni publicar secretos de `.env.*`.
- `core/urls.py`, `core/views.py`: portada `/`, Hub `/index/`, registro de rutas
  del Core y satélites. `core/wsgi.py`/`asgi.py`: entrada de servidor.
- `apps/security/`: alberga los dominios lógicos security, configuration,
  accounts y organigrama; modelos en `models/`, lógica en `services/`, vistas,
  formularios, permisos, migraciones y comandos. Usuario: `security.User`.
- `apps/shared/module_sdk/`: contratos, descubrimiento, registro, integración,
  servicios y rutas de satélites. `module_manifest.py` define el contrato técnico;
  `permissions.py` define roles, llaves y navegación.
- `apps/shared/context_processors.py`, `templatetags/`: contexto institucional,
  navegación y componentes compartidos.
- `apps/shared/workflows/`, `apps/security/workflows/`: guías y diagramas de flujo.
- `templates/shell/base.html`: shell persistente. `templates/navigation/`,
  `partials/`, `components/`: navegación y UI transversal. Login, portada y errores
  son páginas independientes y necesitan sus propios recursos y variables tenant.
- `apps/*/templates/`: páginas, workbench, contenido y fragmentos HTMX.
- `assets/css/tailwind.css`: fuente; `static/css/tailwind.css`: generado versionado.
- `static/js/`, `static/fonts/`: bibliotecas y fuentes locales; inventario en
  `docs/frontend-assets.md`. `tools/tailwind.py`: instalación y compilación.
- `apps/shared/tests/`, `apps/security/tests/`: pruebas Django.
- `Dockerfile`, `docker-compose.*.yml`: build y entornos con PostgreSQL.

## Contratos que preservar

- El Core debe iniciar sin satélites. No importar sus modelos ni agregar sus rutas
  obligatoriamente al Core; usar el SDK y las integraciones opcionales.
- Disponibilidad: instalado + activo + usuario vigente + membresía activa + permiso
  fino. Proteger vistas con `axentra_module_gate`/`axentra_gate_enforcer`.
  Ocultar controles en HTML no sustituye autorización backend.
- `AppModule` guarda estado institucional; `UserAppRole` membresías;
  `permissions_list` el snapshot efectivo. No sobrescribir personalizaciones
  ordinarias al actualizar manifiestos. Los módulos CORE no se desactivan.
- Mantener los contratos HTMX de `#workbench`, `#page-content`, sidebar contextual,
  mensajes fuera de banda e historial. Probar acceso directo y carga parcial.
- Conservar colores por institución como variables CSS runtime. No generar un CSS
  distinto por tenant ni introducir compiladores o CDNs en el navegador.
- No ejecutar migraciones ni aprovisionar usuarios desde el build. Revisar efectos
  de comandos: `check_axentra_modules` sincroniza datos incluso sin `--persist`.

## Frontend y validación

Usar los comandos del README. `uv sync --frozen` instala dependencias.
`uv run python tools/tailwind.py install` descarga el CLI de versión/SHA256 fijados;
`build` compila y `watch` recompila. No requiere Node.js. Actualizar el lock del CLI
solo con hashes de la publicación oficial. No versionar `.tools/`.

Las clases deben aparecer completas. Si se interpolan colores en componentes,
actualizar `@source inline` y las pruebas de cobertura del CSS. Incluir nuevas
fuentes `@source` cuando se agreguen scripts o satélites externos. Recompilar y
versionar el resultado; nunca editar directamente el CSS generado. Descargar
bibliotecas/fuentes a `static/`, fijar versión y documentar procedencia/licencia.

Verificaciones habituales, seleccionando las que correspondan al cambio:

```bash
DJANGO_ENV=build uv run python manage.py check
DJANGO_ENV=build uv run python manage.py test apps.shared.tests apps.security.tests
uv run python tools/tailwind.py build
DJANGO_ENV=build uv run python manage.py collectstatic --noinput
```

Las pruebas usan su base aislada; no usar la base real para fixtures destructivos.
La ausencia de `.env.build` produce una advertencia esperada. No ocultar errores
reales de compilación, referencias a assets faltantes ni fallos de pruebas.
Para cambios visuales, verificar escritorio/móvil, branding, iconos y swaps HTMX.

## Git y documentación

Revisar estado y ramas antes de editar; preservar cambios del usuario. Trabajar en
una rama `fix/...` o `feature/...` desde `develop`. `main` es estable y `develop`
integración: deben recibir los mismos cambios al cerrar una entrega, no mediante
reescritura forzada de historia. No mover ramas históricas solo para alinearlas.
No publicar ni fusionar cambios sin autorización del usuario.

Actualizar README si cambian instalación, configuración, build o despliegue;
actualizar este contexto y la arquitectura cuando cambien sus contratos. Explicar
qué cambió, qué pruebas pasaron y qué verificaciones quedaron pendientes.

## Hoja de ruta activa

Consultar `docs/roadmap/core-hardening.md` para fases, decisiones pendientes y
criterios de aceptación. En Seguridad, `application_selectors.py` centraliza el
alcance y conteos de gobierno; el catálogo `security:applications` pagina en el
servidor y el panel muestra hasta cinco apps. No reintroducir consultas por fila
ni interpretar membresías vigentes como autorización efectiva sobre datos.

## Alcance de datos institucionales

Regla: cada dependencia accede a sus datos; otras dependencias requieren una
autorización explícita, sin herencia jerárquica. El contrato inicial está en
`apps.shared.module_sdk.data_access` y se documenta en
[docs/apps/data-access.md](docs/apps/data-access.md).
El SDK requiere adopción explícita en consumidores y no cambia automáticamente
el alcance administrativo de los paneles existentes. La migración 0010 crea
las autorizaciones; aplicarla antes de utilizar este contrato.

## Fase 3 en OpenProject

Épica OP#37: ramas `feature/OP-38-identidad-password-correo`,
`feature/OP-39-sesiones-panel-revocacion`, `feature/OP-40-privilegios-sudo-reauth`.
Commits citan la subtarea y OP#37; cuerpos de PR incluyen `Closes OP#38`/39/40 y
resultados de pruebas. Trabajo local: no hacer push ni publicar PR sin nueva autorización.
Ver `docs/apps/identity-security.md`: middleware de ciclo de identidad, MFA TOTP,
verificación de correo y cambio inicial. No omitir esos controles en nuevas rutas.

OP#39: `AccountSessionMiddleware` inventaría sesiones y exige revocación antes de las
vistas. Mantener su UUID durante rotaciones de cookie; nunca almacenar/exponer llaves
Django. Panel `accounts:sessions` solo admite sesiones propias y POST con contraseña.
Aplicar 0012 antes de iniciar. REMOTE_ADDR es orientativo, no confiar en XFF.
