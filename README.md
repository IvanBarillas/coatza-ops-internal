# 👑 AXENTRA OS — CORE PLATFORM MANIFESTO

### Chasis Maestro de Infraestructura, Ciberseguridad Centralizada y Software Federado

Este repositorio concentra el Core Engine inmutable de **Axentra OS**. Está diseñado bajo una arquitectura matricial y agnóstica de software de alta velocidad, actuando como el motor maestro y la fuente única de verdad para la distribución de aplicaciones satélites hacia múltiples clientes remotos (Multi-Tenant).

---

## 📂 Directorio Maestro de Documentación (The Hub)

Para preservar el minimalismo radical y evitar la duplicación de especificaciones en la raíz del proyecto, todo el conocimiento técnico, los flujos operativos y los manuales de integración se encuentran encapsulados de forma federada en el directorio de documentación.

📂 **Ruta de Acceso:** `docs/apps/`

### 🛡️ 1. Arquitectura y Gobernanza Central

- **Core Engine Specification (`000_core_architecture`):** El manifiesto técnico obligatorio. Detalla el funcionamiento del guardián de rutas `axentra_module_gate`, la inyección atómica en la RAM del request, el escalafón inmutable de pesos políticos y el protocolo estricto para federar nuevas aplicaciones satélites en el ecosistema.
  ➔ [Abrir Consola de Arquitectura Core](docs/apps/000_core_architecture.md)

### 🎛️ 2. Diccionario de Aplicaciones y Módulos Satélites

_(Este índice se expande conforme el Core Engine distribuye nuevas capacidades a los repositorios de los clientes)._

- **Ciberseguridad y Consola Táctica (`security`):** Administración de la estación , marcas de identidad legal, logs de auditoría forense y mitigación de intrusiones.
  ➔ [Abrir Manual de Ciberseguridad Central](docs/apps/security.md)
- **Estructura Orgánica (`organigrama`):** Gobierno de la matriz intermedia de 3 vías (Sedes, Dependencias y Áreas Operativas).
  ➔ [Abrir Especificación de Organigrama](docs/apps/organigrama.md)
- **Plantilla de Personal (`accounts`):** Expediente laboral digital de funcionarios, control demográfico y mitigación de inconsistencias.
  ➔ [Abrir Manual de Fichas de Identidad](docs/apps/accounts.md)

---

## Licencia

AXENTRA MÉXICO © 2026  
_Infraestructura soberana, tecnologías de ciberseguridad avanzada y sistemas de alto rendimiento para la Administración Pública._

## Desarrollo y recursos frontend locales

Requisitos: Python 3.13+, `uv` y Git. Tailwind usa el CLI **standalone oficial
4.3.3**: no requiere Node.js. Sus ejecutables y SHA256 están fijados en
`tools/tailwind.lock.json`; se descargan a `.tools/` (no versionado).

```bash
uv sync --frozen
# Preparar .env.dev a partir de .env.example y ajustar sus valores.
uv run python tools/tailwind.py install
uv run python tools/tailwind.py build
uv run python manage.py migrate
uv run python manage.py runserver
```

En otra terminal, al editar plantillas, clases Python/JavaScript o el tema:

```bash
uv run python tools/tailwind.py watch
```

Editar `assets/css/tailwind.css`; **no editar el generado**
`static/css/tailwind.css`. Se versiona el CSS generado para disponer de estilos
al clonar y en el bind mount de desarrollo. Regenerarlo antes de entregar cambios.
El escaneo incluye `templates/`, `apps/` (también formularios y fragmentos HTMX)
y los scripts propios enumerados con `@source`. Al agregar un script o un
satélite fuera de esas rutas, registrar su fuente.

Las clases de Alpine/HTMX deben aparecer completas en el código. Los componentes
que interpolan colores usan la lista explícita `@source inline` del CSS fuente;
al ampliar su paleta, ampliar esa lista y verificar el CSS resultante. Los colores
`brand-primary`, `brand-secondary` y `brand-accent` se generan durante el build,
y cada página define sus valores mediante variables CSS `:root` del tenant.
Cambiar los colores institucionales no necesita recompilar.

Tailwind Browser/Play CDN y Google Fonts ya no se cargan en el navegador. Lucide,
HTMX, Alpine, Chart.js, Mermaid y Source Sans 3 se sirven desde `static/`.
El inventario y las licencias están documentados en `docs/frontend-assets.md`.
La instalación inicial del compilador requiere Internet; compilar con el CLI ya
instalado y servir los recursos frontend no lo requieren. Los enlaces de usuario
como WhatsApp siguen siendo enlaces externos.

## Build y despliegue

El `Dockerfile` instala el CLI verificado, compila CSS y después ejecuta
`collectstatic`. WhiteNoise usa `STORAGES` de Django 6 para generar nombres con
hash y archivos comprimidos. `docker-compose.prod.yml` sirve los estáticos de la
imagen: no monta un volumen persistente sobre `/app/staticfiles`, evitando CSS
antiguo después de reconstruir. Los volúmenes de base de datos, media y logs se
mantienen. Un volumen `static_data` de despliegues anteriores queda sin usar; no
es necesario eliminarlo para desplegar.

```bash
# Comprobación local sin depender de .env.dev ni tocar la base de datos real:
DJANGO_ENV=build uv run python manage.py check
DJANGO_ENV=build uv run python manage.py test apps.shared.tests apps.security.tests
uv run python tools/tailwind.py build
DJANGO_ENV=build uv run python manage.py collectstatic --noinput

# Con .env.prod preparado:
podman-compose --env-file .env.prod -p axentra-municipio -f docker-compose.prod.yml up --build -d
```

La advertencia de `.env.build` ausente es esperada: el build usa valores por
defecto sin secretos. `migrate` y el aprovisionamiento del operador inicial son
pasos operativos independientes; el build no modifica la base de datos.
En desarrollo con contenedores, ejecutar `watch` en el host (el repositorio está
montado en `/app`); consultar `docker-compose.dev.yml` para `.env.container`.

## Ramas y contexto para agentes

`main` representa la versión estable y `develop` la integración. Crear ramas
`feature/...` o `fix/...` desde `develop`, revisar y probar antes de integrar.
Al finalizar una entrega, promover los mismos cambios a `main` y comprobar su
alineación con `develop`; durante el desarrollo pueden diferir. No igualarlas
con `reset --hard` ni `push --force`. Las ramas históricas de funcionalidades no
necesitan apuntar al mismo commit.

Consultar [AGENTS.md](AGENTS.md) antes de modificar el proyecto y actualizar este
README cuando cambien comandos de instalación, compilación o despliegue.

## Fortalecimiento del Core por fases

La hoja de ruta y criterios de aceptación están en
[docs/roadmap/core-hardening.md](docs/roadmap/core-hardening.md).
La fase 1 limita el resumen de Seguridad a cinco aplicaciones y añade
**Aplicaciones y accesos** al sidebar, con búsqueda, filtro por owner y páginas
de 20 resultados dentro del alcance del usuario. Las métricas cuentan membresías
vigentes de usuarios activos y excluyen bajas lógicas; no certifican permisos
finos ni la salud de cada módulo. El Hub conserva la activación de aplicaciones.

## Instalaciones municipales independientes

Cada ayuntamiento tiene su propia instalación y base de datos. También se separan
secretos, media, logs, caché y respaldos. Consultar
[la guía de instalaciones](docs/deployment/municipal-installations.md).

En un host con varios ayuntamientos, usar proyectos Compose distintos (`-p`),
puertos distintos (`AXENTRA_HTTP_PORT`) y dominios HTTPS propios. Usar
`--env-file .env.prod` para interpolar los puertos; la publicación predeterminada
es `127.0.0.1:8000`, destinada a un proxy en el host. Producción lee
`CSRF_TRUSTED_ORIGINS` del entorno de cada institución.

## Alcance de datos institucionales

Regla: cada dependencia accede a sus datos; otras dependencias requieren una
autorización explícita, sin herencia jerárquica. El contrato inicial está en
`apps.shared.module_sdk.data_access` y se documenta en
[docs/apps/data-access.md](docs/apps/data-access.md).
El SDK requiere adopción explícita en consumidores y no cambia automáticamente
el alcance administrativo de los paneles existentes. La migración 0010 crea
las autorizaciones; aplicarla antes de utilizar este contrato.

## Identidad — OP#38 / Fase 3 OP#37

El acceso exige reemplazar contraseñas provisionales, completar TOTP en cuentas
administrativas y verificar el correo. **Mi cuenta** concentra estas opciones.
Consultar [el procedimiento de identidad](docs/apps/identity-security.md) antes de
desplegar: se necesitan `uv sync --frozen`, migraciones django-otp/0011 y SMTP
configurado. Las sesiones anteriores deberán iniciar sesión nuevamente.
