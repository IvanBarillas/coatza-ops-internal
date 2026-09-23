# Roadmap hacia producción robusta — Axentra Core

Este documento **no reemplaza** `docs/roadmap/core-hardening.md` (que ya define las Fases 1–7
del hardening funcional: paneles, aislamiento de datos, identidad, auditoría, organigrama,
configuración y validación con satélites reales). Lo complementa desde un ángulo distinto:
**operación e infraestructura** — lo que hace falta para que una instalación real de un
ayuntamiento sea confiable día a día, no solo funcionalmente correcta.

Fuente: lectura directa de `core/settings/{base,production}.py`, `.github/workflows/ci.yml`,
`Dockerfile`, `docker-compose.prod.yml`, `deploy/podman-ops/` (RUNBOOK incluido), `pyproject.toml`,
`docs/roadmap/core-hardening.md`, `docs/reviews/*`, `tools/continuity.py`,
`apps/security/management/commands/check_operational_health.py`, `README.md`. Cada punto indica
qué ya existe y qué falta; no se propone nada que contradiga las decisiones ya tomadas en el
repo (una instalación/BD por ayuntamiento, sin Redis/RabbitMQ, sin multi-tenancy compartido).

**Estado real del repo hoy, en sus propias palabras**: el propio roadmap interno marca las
Fases 5, 6 y 7 como *Pendiente*, y la Fase 3 (identidad/sesiones/privilegios) y Fase 4
(auditoría/continuidad) como *"validación operativa pendiente"* — es decir, implementadas y
probadas en SQLite local, **nunca ensayadas contra PostgreSQL real ni una instalación real**.
El propio RUNBOOK de despliegue se autodenomina *"entorno semi real DEV"* y marca Traefik, DNS,
certificados y paridad con Hermes como **`[no probado]`**. Ningún flujo de este roadmap debe
darse por completo solo porque el código exista: falta el ensayo operativo en cada caso.

---

## Cómo leer las prioridades

- 🔴 **Crítico** — bloquea salir a producción con datos reales de un ayuntamiento.
- 🟠 **Alto** — no bloquea el primer despliegue, pero es alto riesgo operativo a corto plazo.
- 🟡 **Medio** — mejora robustez/mantenibilidad; puede esperar a después del primer municipio.
- ⚪ **Bajo** — pulido, no urgente.

---

## 1. 🔴 Observabilidad y monitoreo de errores en producción — 🟡 parcialmente resuelto (2026-09-22)

**Ya existe**: `check_operational_health` (comando que prueba BD + caché, salida JSON, código de
salida no-cero — pensado para un monitor externo tipo cron/systemd), `healthcheck.py` en
`deploy/podman-ops/`, y `AxentraRadar` (`apps.shared.utils.telemetry`) para telemetría de
diagnóstico en desarrollo. **Resuelto ahora**: `LOGGING` en `core/settings/production.py` usa
`RotatingFileHandler` (10 MB × 5 archivos por defecto, configurable vía `LOG_MAX_BYTES`/
`LOG_BACKUP_COUNT`) en vez de `FileHandler` — el log ya no crece sin límite. **Resuelto ahora**:
`check_operational_health` quedó enlazado como `HEALTHCHECK` del `Dockerfile` y como
`healthcheck:` de `web`/`worker` en `docker-compose.prod.yml` (ver §5) — un orquestador ya puede
detectar y reiniciar un contenedor colgado.

**Sigue faltando**:
- **No hay ningún integrador de error-tracking (Sentry, GlitchTip, etc.)** — sigue sin existir
  ningún canal que avise a un humano cuando algo truena a las 3am; la rotación de logs evita
  llenar disco, pero nadie lee ese archivo en tiempo real.
- No hay `/health/` ni `/status/` expuesto por **HTTP** — el healthcheck nuevo corre el comando
  *dentro* del contenedor (vía `docker/podman healthcheck`, no por la red), que es suficiente para
  que el orquestador reinicie el proceso, pero no sirve como probe de un balanceador/Traefik
  externo si se necesitara verificar salud desde fuera del host.
- No hay métricas (Prometheus/StatsD) de latencia, tasa de error por vista, cola de Django-Q2
  (tareas pendientes/fallidas), ni dashboard operativo. `docs/roadmap/core-hardening.md`
  Fase 4 dice *"alertas conectadas"* como pendiente explícito.

**Acción sugerida**: Sentry (o self-hosted GlitchTip, dado el enfoque de soberanía de datos del
proyecto) con DSN por instalación sigue siendo lo más importante pendiente de este punto.

---

## 2. 🔴 CI/CD incompleto — solo valida, no protege ni despliega

**Ya existe** (`.github/workflows/ci.yml`): un solo job que corre `manage.py check`,
`collectstatic` y `manage.py test` en cada push/PR a `main`/`develop`. Es un buen punto de
partida y ya evita el "se me olvidó correr las pruebas".

**Falta**:
- **Sin linting** (ruff/flake8), **sin formateo verificado** (black/ruff format), **sin type
  checking** (mypy/pyright), **sin análisis de seguridad estático** (bandit) ni **auditoría de
  dependencias** (`pip-audit`/`safety`/`uv`'s propio audit) — `pyproject.toml` no declara
  ningún grupo de dependencias de desarrollo (no hay `[dependency-groups]`/`[tool.ruff]`/
  `[tool.mypy]`), y no existe `.pre-commit-config.yaml`. Nada impide mergear código con
  vulnerabilidades conocidas en dependencias o con `bandit`-flags (uso de `eval`, SQL crudo,
  secretos hardcodeados) sin que nadie lo note.
- **Sin medición de cobertura** (`coverage.py`/`pytest-cov`) — no hay forma de saber qué
  porcentaje del código de negocio está bajo prueba, ni de exigir un mínimo en CI.
- **Sin verificación de `makemigrations --check --dry-run` en CI** — el roadmap interno lo
  corre manualmente antes de cada fase (`docs/roadmap/core-hardening.md:183`), pero no está
  automatizado; es fácil que a alguien se le olvide y llegue una migración faltante a `main`.
- **Sin build de la imagen Docker/Containerfile en CI** — el `Dockerfile` y
  `deploy/podman-ops/Containerfile` nunca se construyen automáticamente; un `Dockerfile` roto
  solo se descubre al desplegar.
- **Sin CD**: no hay ningún workflow de despliegue automático (ni siquiera a un entorno de
  staging). Todo el despliegue documentado en `deploy/podman-ops/RUNBOOK.md` es manual, paso a
  paso, ejecutado por una persona en la terminal del host — sin rollback automatizado.
- Un solo job, sin matriz de versiones ni separación por tipo de prueba (rápidas vs. lentas).

**Acción sugerida**: agregar jobs de `ruff check`, `ruff format --check`, `bandit -r apps core`,
`pip-audit` (o `uv pip audit` cuando esté disponible), `coverage run manage.py test` con umbral
mínimo, y `makemigrations --check --dry-run`, todos en paralelo al job actual. Añadir un job que
construya la imagen Docker (sin publicarla) para detectar roturas de build temprano.

---

## 3. 🔴 Backups: el código existe, la operación no

**Ya existe**: `tools/continuity.py` implementa respaldo/verificación/restauración con manifiesto
JSON, hashes SHA256 por archivo, `PRAGMA integrity_check` para SQLite, y explícitamente rechaza
symlinks y contenido no declarado — es un diseño cuidadoso. La Fase 4 del roadmap interno declara
esto "implementación inicial... ensayo SQLite" con **"validación PostgreSQL/operativa pendiente"**.

**Falta**:
- **Nada lo ejecuta automáticamente**. No hay cron/systemd timer/Quadlet-timer que corra el
  respaldo con una periodicidad definida; depende de que alguien lo invoque a mano.
- **No hay copia fuera del host** (offsite/objeto remoto tipo S3-compatible/rsync a otro
  servidor). El propio roadmap lo marca pendiente ("copia externa protegida").
- **No hay RPO/RTO acordado con ninguna institución** ni ensayo de restauración cronometrado —
  solo un simulacro aislado en SQLite (Fase 4), nunca contra PostgreSQL real.
- `docker-compose.prod.yml` y los Quadlets de `deploy/podman-ops/` no incluyen ningún servicio
  ni volumen dedicado a respaldos — los volúmenes (`postgres_prod_data`, `media_data`,
  `logs_data`) viven únicamente en el host, sin réplica.

**Acción sugerida**: un Quadlet `.timer` (o cron del host) que invoque `tools/continuity.py`
respaldo diario, con subida a almacenamiento externo cifrado, retención definida (p. ej. 30
diarios + 12 mensuales) y una alerta si el respaldo falla o si `verify` detecta corrupción.
Ensayar restauración completa contra PostgreSQL al menos una vez antes del primer municipio
real, y documentar el tiempo que tomó.

---

## 4. 🟠 Endurecimiento HTTP faltante en `production.py` — ✅ HSTS resuelto (2026-09-22)

`core/settings/production.py` ya cubre lo esencial: `DEBUG=False` inmutable, `SECRET_KEY`/
`ALLOWED_HOSTS` desde entorno, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`,
`SECURE_SSL_REDIRECT` (con `SECURE_REDIRECT_EXEMPT` para la API interna),
`SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS` por institución, `CONN_MAX_AGE`/
`CONN_HEALTH_CHECKS`/`ATOMIC_REQUESTS` en BD, y `EMAIL_TIMEOUT` explícito. `base.py` también
define `SECURE_CONTENT_TYPE_NOSNIFF = True` y `X_FRAME_OPTIONS = 'DENY'` globalmente, más
`django-axes` para fuerza bruta de login (`AXES_FAILURE_LIMIT=5`, `AXES_COOLOFF_TIME=1`).

**Resuelto**: `SECURE_HSTS_SECONDS` (`core/settings/production.py`), configurable vía entorno con
default conservador de 3600s (1 hora) — subir a 31536000 (1 año) solo tras confirmar HTTPS estable
en todos los subdominios de la institución. `SECURE_HSTS_INCLUDE_SUBDOMAINS`/`SECURE_HSTS_PRELOAD`
también agregados, ambos en `False` por defecto (activarlos es una decisión explícita posterior,
no algo seguro de asumir de entrada). Verificado con `manage.py check --deploy`: el warning
`security.W004` (HSTS ausente) ya no aparece.

**Sigue faltando**:
- **No hay Content-Security-Policy** (ni cabecera manual ni `django-csp`) — nada limita de qué
  orígenes puede cargar script/estilo/imagen el navegador; dado que el proyecto ya prohíbe CDNs
  en el navegador (AGENTS.md), un CSP estricto sería barato de adoptar y cerraría XSS residual.
- **Sin rate limiting genérico de vistas/API** — `django-axes` cubre fuerza bruta de login y
  `OTP_TOTP_THROTTLE_FACTOR` cubre TOTP, pero no hay nada que limite ráfagas contra otras vistas
  públicas (formularios ciudadanos, endpoints de `api_urlconf` de satélites) o contra el propio
  `/directorio/` público.
- `manage.py check --deploy` no corre en CI (§2) — es el comando que Django ofrece
  específicamente para detectar estos huecos; correrlo automáticamente evitaría que se repita
  este tipo de brecha en el futuro.

**Acción sugerida**: agregar `SECURE_HSTS_SECONDS` (empezar bajo, p. ej. 3600, y subir tras
confirmar que todo sirve por HTTPS), evaluar `django-csp` o cabecera manual, y correr
`manage.py check --deploy` como paso obligatorio de CI contra `core.settings.production`.

---

## 5. 🟠 Contenedores: healthcheck de aplicación — ✅ resuelto (2026-09-22); gestión de recursos aún falta

**Ya existía**: `Dockerfile` con usuario no-root (`axentra`, UID 1000, sin shell de login),
`.dockerignore`, build reproducible con `uv sync --frozen`. `docker-compose.prod.yml` tenía
healthcheck para `db` (Postgres) y usa `depends_on: condition: service_healthy`. El RUNBOOK de
Podman pasa secretos por tubería (nunca a archivo) y usa `podman secret`.

**Resuelto ahora**: `Dockerfile` define `HEALTHCHECK` (reutiliza `check_operational_health` —
BD+caché, sin asumir satélites instalados, a diferencia de `deploy/podman-ops/healthcheck.py` que
sí asume el satélite Trámites y por eso no aplicaba aquí). `docker-compose.prod.yml` replica el
mismo chequeo explícitamente en `healthcheck:` de `web` **y** `worker` (antes solo `db` lo tenía).
Si Gunicorn o `qcluster` cuelgan sin caerse, Podman/Docker ahora lo detecta y puede reiniciar el
contenedor según su política de `restart`.

**Sigue faltando**:
- **`docker-compose.prod.yml` no define límites de recursos** (`mem_limit`/`cpus` o el
  equivalente `deploy.resources` de Compose v3) — un satélite o fuga de memoria puede tumbar el
  host completo sin ningún límite duro.
- El Dockerfile no es multi-stage (build de Tailwind y dependencias de compilación quedan en la
  imagen final) — no es incorrecto, pero infla el tamaño de imagen; considerar separar build de
  runtime si el tamaño se vuelve un problema operativo.
- No hay política de actualización de la imagen base (`python:3.13-slim`) ni de escaneo de
  vulnerabilidades de la imagen (Trivy/Grype) en CI.

**Acción sugerida**: definir límites de memoria/CPU por servicio en `docker-compose.prod.yml` y
replicar el mismo `HealthCmd` en los Quadlets de `deploy/podman-ops/axentra-core-worker.container`
(hoy solo `axentra-core.container` lo tiene, ver `deploy/podman-ops/quadlet/`).

---

## 6. 🟠 Validación operativa real pendiente (lo dice el propio roadmap)

Esto no es un gap nuevo — es la lectura consolidada de lo que `docs/roadmap/core-hardening.md`
y `docs/reviews/*` ya marcan como pendiente, reunido aquí porque bloquea producción real:

- Migraciones 0011–0013 (sesiones, sudo, autoridad técnica) y **django-otp nunca aplicadas a una
  BD PostgreSQL real** — todo el ensayo es SQLite local.
- SMTP real nunca probado end-to-end (verificación de correo, recuperación de contraseña,
  notificaciones) — solo backend de archivo/consola en desarrollo.
- Simulacro de restauración de auditoría/continuidad solo se hizo en SQLite aislado
  (`docs/roadmap/core-hardening.md:234-236`): *"No se aplicó 0014 a la BD real"*, *"No se
  ejecutaron herramientas PostgreSQL contra un servidor"*.
- El RUNBOOK de Podman se autodescribe como *"entorno semi real DEV"* con Traefik, DNS,
  certificados y paridad con Hermes marcados **`[no probado]`** — es decir, el único ensayo de
  despliegue multi-satélite documentado en el repo todavía no se completó contra
  infraestructura real de producción.
- Fase 3 pide *"recuperación operativa y responsabilidades institucionales... ensayar antes de
  producción"* — sin un municipio piloto real, esto sigue en el papel.

**Acción sugerida**: antes de aceptar el primer municipio en producción, ejecutar un ensayo
integral contra PostgreSQL real: migrar, `check_axentra_modules --persist`,
`bootstrap_axentra_owner`, disparar correo real (verificación + reset), simular fallo del
auditor, respaldar y restaurar completo, medir el tiempo de cada paso. Documentar el resultado
en `docs/reviews/` como evidencia, igual que se hizo con OP-38/39/40.

---

## 7. 🟡 Cumplimiento de protección de datos (LFPDPPP) — base puesta, faltan piezas operativas

**Ya existe**: `TenantConfig` con campos de privacidad/cookies (migración `0016`), vista y
pruebas de `privacidad_cookies` (`apps/security/tests/test_privacidad_cookies.py`) — un aviso de
privacidad único por instalación en vez de uno duplicado por satélite (decisión documentada en
`docs/apps/public-municipal-portal.md`). Auditoría (`SecurityAuditLog`) con correlación por
petición, actor de sistema y protección ante alteración de eventos ya implementada (Fase 4).

**Falta** (deducido; no hay evidencia en el repo de que esto exista):
- **Sin flujo de derechos ARCO** (Acceso, Rectificación, Cancelación, Oposición) — ni exportación
  de datos personales de un titular ni borrado/anonimización bajo solicitud.
- **Sin política de retención de datos** explícita ni purga automática de datos vencidos
  (sesiones expiradas sí se limpian vía revocación, pero no hay ciclo de vida documentado para
  expedientes, logs de auditoría a largo plazo, etc. — Fase 4 lo deja como "conservación...
  pendiente").
- **Sin cifrado en reposo** documentado para la base de datos o `media/` — depende
  completamente del cifrado de disco del host, no del propio Core.
- **Sin bitácora específica de "quién accedió a qué dato personal"** más allá de la auditoría de
  escritura HTTP genérica — `AuditTransactionMiddleware` cubre mutaciones, no necesariamente
  consultas de lectura sensibles (p. ej. un admin consultando el expediente de un ciudadano).

**Acción sugerida**: dado que cada municipio es su propio responsable de datos (instalación
separada), documentar qué parte del cumplimiento LFPDPPP es responsabilidad del Core vs. del
ayuntamiento como operador, e implementar al menos exportación/anonimización de un usuario bajo
demanda antes de manejar datos ciudadanos reales (satélites de Trámites/Ciudadanía).

---

## 8. 🟡 Documentación pública inconsistente con la arquitectura real

**✅ Resuelto (2026-09-22).** `README.md` describía el proyecto como "Multi-Tenant"
(*"motor maestro... para la distribución de aplicaciones satélites hacia múltiples clientes
remotos (Multi-Tenant)"*), contradiciendo la decisión explícita de `AGENTS.md` y
`docs/roadmap/core-hardening.md`: **una instalación y una base de datos por ayuntamiento, sin
multi-tenancy compartido**. Se corrigió la descripción inicial del README para hablar de
"distribución federada de aplicaciones satélites" con instalación/BD independiente por cliente, y
se enlazó `docs/apps/000_core_architecture.md` como fuente de verdad arquitectónica desde ese
mismo párrafo.

---

## 9. 🟡 Escalar a "muchos ayuntamientos" es 100% manual hoy

Dado que cada municipio es una instalación independiente (decisión correcta y deliberada para
aislamiento de datos), el costo operativo crece linealmente con cada nuevo cliente:

**Ya existe**: `deploy/podman-ops/build.sh` construye la imagen desde 4 repos hermanos con
referencias de commit fijas y las deja etiquetadas en la imagen (`mx.axentra.versiones`) — buen
punto de partida para trazabilidad.

**Falta**:
- **Sin herramienta de gestión de flota**: no hay inventario centralizado de qué versión corre
  cada municipio, ni forma de disparar una actualización coordinada a varias instalaciones desde
  un solo lugar — todo el RUNBOOK asume que una persona opera un host a la vez.
- **Sin plantilla de aprovisionamiento repetible** más allá del RUNBOOK manual (que ya es bueno
  como documento, pero no es Ansible/Terraform/script idempotente) — cada municipio nuevo
  implica repetir ~10 pasos manuales de una persona con acceso al host.
- **Sin canal de actualización de seguridad urgente**: si aparece una CVE crítica en una
  dependencia, no hay mecanismo para notificar/parchear todas las instalaciones activas más
  rápido que "ir una por una".

**Acción sugerida**: no es bloqueante para el primer municipio, pero antes del tercer/cuarto
cliente conviene automatizar aprovisionamiento (Ansible playbook sobre el RUNBOOK existente) y
llevar un inventario mínimo (aunque sea una hoja de cálculo firmada por versión/commit/fecha de
último parche) de qué corre cada instalación.

---

## 10. ⚪ Higiene de proyecto menor

- `pyproject.toml` tiene `description = "Add your description here"` (placeholder de plantilla,
  nunca reemplazado) y `version = "0.1.0"` sin política de versionado visible (no hay
  `CHANGELOG.md` ni tags de release en el flujo documentado).
- No hay `SECURITY.md` con proceso de reporte responsable de vulnerabilidades, relevante para un
  proyecto que se autodescribe con foco en "ciberseguridad centralizada".
- `USE_I18N = True` y `LANGUAGE_CODE = 'es-mx'` están configurados, pero no existe carpeta
  `locale/` — si el objetivo real es un solo idioma (español mexicano fijo, sin necesidad de
  cambiar de idioma en runtime), `USE_I18N` podría desactivarse para ahorrar el overhead de
  Django resolviendo idioma en cada request; si el objetivo es soportar más de un idioma a
  futuro, falta la infraestructura de traducción (`makemessages`/`compilemessages`, archivos
  `.po`).

---

## Resumen priorizado

| # | Tema | Prioridad | Bloquea 1er municipio real | Estado |
|---|---|---|---|---|
| 1 | Error-tracking (Sentry) + rotación de logs + `/health/` HTTP | 🔴 | Sí | 🟡 rotación de logs + healthcheck de contenedor resueltos; falta Sentry y probe HTTP externo |
| 2 | CI: lint, type-check, seguridad (bandit/pip-audit), cobertura, check de migraciones, build Docker | 🔴 | Recomendado antes | Pendiente |
| 3 | Backups automatizados + offsite + ensayo de restauración PostgreSQL | 🔴 | Sí | Pendiente |
| 4 | `SECURE_HSTS_SECONDS`, CSP, rate limiting general, `check --deploy` en CI | 🟠 | Recomendado antes | 🟢 HSTS resuelto; falta CSP, rate limiting y automatizar `check --deploy` en CI |
| 5 | Healthcheck de `web`/`worker` en Compose/Quadlet, límites de recursos | 🟠 | Recomendado antes | 🟢 healthcheck resuelto (Compose); falta en Quadlet worker y límites de recursos |
| 6 | Ensayo integral contra PostgreSQL real (migraciones, SMTP, auditoría, restore) | 🔴 | Sí | Pendiente |
| 7 | Derechos ARCO, retención de datos, cifrado en reposo | 🟡 | Solo si maneja datos ciudadanos (Trámites/Ciudadanía) | Pendiente |
| 8 | Corregir README (Multi-Tenant → instalación federada por cliente) | 🟡 | No, pero genera confusión | ✅ Resuelto |
| 9 | Automatizar aprovisionamiento/gestión de flota | 🟡 | No, importa al escalar clientes | Pendiente |
| 10 | Higiene menor (SECURITY.md, changelog, i18n real o desactivar) | ⚪ | No | Pendiente |

**Lectura de conjunto**: el Core tiene una base de seguridad funcional notablemente madura
(auditoría con correlación, SUDO, MFA, aislamiento de datos por dependencia, respaldo con
verificación SHA256) — el trabajo pendiente de mayor riesgo **no es funcional, es operativo**:
nadie ha visto fallar este sistema en PostgreSQL real, nadie ha restaurado un respaldo real bajo
presión, y no hay ningún ojo automatizado (Sentry, alertas, CI de seguridad) vigilando una vez
que el código ya está corriendo. Priorizar #1 (falta Sentry), #3 y #6 antes de aceptar el primer
municipio en producción; el resto puede entrar en paralelo con las Fases 5–7 ya planeadas en
`docs/roadmap/core-hardening.md`.

### Cambios ya aplicados en esta sesión (2026-09-22)

Los tres ajustes de menor esfuerzo/riesgo del roadmap ya se implementaron y se verificaron con
`manage.py check` / `check --deploy`:

1. **README** — descripción corregida de "Multi-Tenant" a instalación federada por cliente, con
   enlace a `docs/apps/000_core_architecture.md`.
2. **`core/settings/production.py`** — `SECURE_HSTS_SECONDS`/`SECURE_HSTS_INCLUDE_SUBDOMAINS`/
   `SECURE_HSTS_PRELOAD` (default conservador, configurable por entorno) y `LOGGING` migrado de
   `FileHandler` a `RotatingFileHandler` (10 MB × 5 archivos por defecto).
3. **`Dockerfile` + `docker-compose.prod.yml`** — `HEALTHCHECK`/`healthcheck:` para `web` y
   `worker` reutilizando `manage.py check_operational_health` (BD + caché, no asume satélites).

Ninguno de los tres requirió tocar `core/urls.py`, modelos ni contratos del `module_sdk` — son
cambios de configuración/infraestructura aislados, consistentes con las reglas de `AGENTS.md`.
