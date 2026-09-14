# Fortalecimiento del Core municipal por fases

Estado inicial: diagnóstico del Core después de integrar frontend local (`e740ca8`).
Esta hoja distingue correcciones comprobadas de propuestas que requieren definir
contratos. Cada fase entrega código, pruebas, documentación y evidencia antes de
iniciar la siguiente. No fusionar ni publicar una fase sin autorización.

| Fase | Entrega | Estado |
| --- | --- | --- |
| 1 | Panel y catálogo de aplicaciones escalables | Implementada y validada localmente |
| 2 | Aislamiento municipal y autorización sobre datos | Contrato inicial implementado; adopción por consumidores pendiente |
| 3 | Identidad, sesiones y privilegios administrativos | OP#38–40 implementadas localmente; validación operativa pendiente |
| 4 | Auditoría y continuidad operativa | Implementación inicial y ensayo SQLite; validación PostgreSQL/operativa pendiente |
| 5 | Organigrama e historial de adscripciones | Pendiente |
| 6 | Configuración institucional y servicios compartidos | Pendiente |
| 7 | Validación con satélites municipales reales | Pendiente |

## Fase 1 — Panel y aplicaciones

- Sustituir las consultas por aplicación por agregaciones y subconsultas SQL.
- Excluir bajas lógicas y usuarios inactivos de conteos de membresías vigentes.
  Estos conteos no certifican por sí solos permiso fino ni salud del módulo.
- Mantener un resumen acotado en inicio y llevar el listado completo a
  Seguridad → Aplicaciones y accesos, con búsqueda, filtros y paginación servidor.
- Respetar alcance: administradores globales y owners vigentes de cada app.
- Reemplazar mensajes generales de seguridad por resultados específicos.
- Mantener Hub como control de disponibilidad y matriz como administración de
  permisos; el catálogo enlaza a la matriz sin duplicar esas funciones.
- Corregir indicadores analíticos que usan catálogos estáticos.

Aceptación: 100 aplicaciones no implican consultas proporcionales por fila;
catálogo paginado de 20 filas, búsqueda/filtros conservados al paginar, ausencia
de datos ajenos para owners delegados, pruebas de bajas/inactivos, navegación
normal y HTMX (`#workbench`, `#page-content`), CSS recompilado y collectstatic.

## Fase 2 — Aislamiento y alcance de datos

Decisión confirmada por el usuario: **cada ayuntamiento tiene su propia instalación
y base de datos**. TenantConfig identifica esa institución dentro de su instancia.
No se introduce selección de municipio por request ni tablas compartidas entre
ayuntamientos. Separar también archivos, secretos, caché, respaldos y servicios.
Regla confirmada: datos de la dependencia propia; cualquier acceso a otra requiere
autorización explícita. Sin herencia por jerarquía. El contrato inicial cubre
dependencia y excepciones por usuario/app/operación; otras restricciones se
definirán con cada consumidor.
Crear contratos comunes de filtrado y autorización por objeto que consuman los
satélites; denegación por defecto, sin deducir permisos del correo o del puesto.

Aceptación: separación operativa entre instalaciones y pruebas negativas entre
dependencias, IDs manipulados,
consultas y exportaciones. Documentar migración y compatibilidad del SDK.

## Fase 3 — Identidad y privilegios

Implementar cambio inicial de contraseña obligatorio y verificar el flujo real de
correo verificado; MFA y recuperación segura para administradores; administración
y revocación de sesiones. Separar administrador técnico de autorizador funcional,
con procedimiento de acceso excepcional. Definir identidad ciudadana separada del
expediente laboral, manteniendo UUID como identidad estable.

Decisión: TOTP local con códigos de recuperación. SSO queda opcional; recuperación
operativa y responsabilidades institucionales se deben ensayar antes de producción.
Aceptación: cuentas inactivas/bajas sin acceso, sesiones revocadas, flujos de
recuperación probados y compatibilidad de cuentas existentes.

## Fase 4 — Auditoría y continuidad

Definir operaciones que requieren evidencia obligatoria y qué hacer si falla su
registro. Añadir antes/después, correlación, actores de sistema y protección ante
alteraciones. Revisar confianza en cabeceras IP del proxy. Definir conservación,
accesos al registro y alertas. Implementar monitoreo, respaldos de BD y archivos y
simulacros de restauración; acordar tiempos de recuperación y pérdida tolerable.

Aceptación: fallo simulado del auditor y recuperación documentada con evidencia;
no confundir presencia de logs con inmutabilidad ni respaldo con restauración.

## Fase 5 — Organización y adscripciones

Decidir si ÁreaOperativa representa unidad administrativa o ubicación de oficina.
Separar unidad y ubicación cuando una misma área opere en varias sedes. Crear
adscripciones con vigencia, principal/secundaria, puesto y encargos temporales.
Conservar la adscripción histórica en actos de cada satélite. Reforzar prevención
de ciclos fuera de formularios para cubrir servicios/importaciones/API.

Aceptación: traslado entre dependencias sin alterar atribución histórica, cambios
de titulares, múltiples sedes y ciclos rechazados. Migración compatible del perfil.

## Fase 6 — Configuración y servicios compartidos

- Periodos de administración, vigencias y calendarios institucionales.
- Identidad municipal por estado + municipio (revisar unicidad actual del código).
- Parámetros identificados por código/tipo/vigencia; permitir varios CUSTOM al año.
- Configuración por módulo tipada y auditada, sin concentrar reglas en TenantConfig.
- Documentos públicos/privados, versiones, límites y tratamiento de cargas.
- Notificaciones y tareas persistentes con reintentos y prevención de duplicados.

Decisiones: almacenamiento, canales de envío y cola de trabajo. Secretos fuera de
BD/configuración visual sin un mecanismo de protección definido.
Aceptación: permisos de archivos y reintentos probados; sin dependencias obligatorias
entre satélites; consumidores de calendarios definen sus reglas de cómputo.

## Fase 7 — Prueba del contrato con apps reales

Validar con eventos, trámites, transparencia y alertas según el orden de negocio.
Core ofrece identidad, organización, autorización, auditoría y servicios comunes;
los satélites conservan expedientes, publicaciones y reglas propias.

Aceptación: apps ausentes/desactivadas sin romper Core, instalación/actualización
reproducible, mediciones con datos representativos, pruebas de autorización,
restauración y publicación/retiro de contenido. Revisar necesidades normativas
específicas por municipio y proceso sin presumir cumplimiento por tener el Core.

## Registro de avance

- Hoja creada: primera entrega limitada a fase 1. Fases posteriores se abordan en
  orden, resolviendo sus decisiones antes de cambios estructurales de datos.

### Evidencia de fase 1

Rama: `feature/core-hardening-phase-1`. Sin migraciones de datos.

- Selector de resumen: **4 consultas SQL** para un owner con una app y para
  administrador global con más de 100 apps. Es el presupuesto del selector,
  no de toda la petición ni una medición de latencia de producción.
- Suite: **48 pruebas pasan**, incluyendo 11 nuevas de gobierno de aplicaciones.
- Cubierto: alcance delegado, bajas lógicas, usuarios inactivos, owners suspendidos,
  búsqueda ajena, catálogo vacío, filtros/paginación, consultas agrupadas y targets HTMX.
- Django check, compilación Tailwind y collectstatic completados.
- Chromium con fixtures de 100 aplicaciones a 1440 y 390 px: panel → catálogo →
  página 2 → historial. 20 filas, iconos locales, sin overflow horizontal, errores
  JavaScript, recursos faltantes ni solicitudes CDN. Los permisos se verificaron
  mediante pruebas Django, no con esos fixtures visuales.
- Corrección encontrada durante validación: `LOGIN_URL` apuntaba a `login`, ruta
  inexistente; ahora usa `accounts:login`, cubierta por acceso anónimo al catálogo.

Decisión de fase 2 confirmada: instalación y base de datos independientes por
ayuntamiento. Regla confirmada: dependencia propia y excepciones explícitas, sin
herencia jerárquica.
La fase 1 no modifica bypass administrativo ni introduce aislamiento multi-tenant.

### Fase 2 — avance de aislamiento por instalación

- Confirmado: una instalación y BD por ayuntamiento. Decisión reflejada en
  arquitectura, AGENTS.md, README y guía de despliegue municipal.
- Producción toma CSRF_TRUSTED_ORIGINS del entorno de la institución.
- Puerto externo configurable y enlace predeterminado al loopback del host;
  proyectos Compose, dominios y volúmenes separados por municipio.
- `.env.example` documenta variables de producción y SMTP.
- **49 pruebas pasan**: incluye producción con orígenes diferentes por institución
  y sin un dominio fijo compartido; cookies seguras permanecen habilitadas.
- No se desplegaron municipios reales ni se verificó aislamiento de infraestructura
  en un servidor. No está instalado podman-compose en este entorno.
- La decisión posterior de acceso explícito se implementa en el contrato descrito
  a continuación; los paneles administrativos existentes conservan su alcance.

### Contrato de alcance implementado

- `DepartmentAccessGrant` y migración 0010: excepción revocable, con origen, destino,
  app, usuario, operación, motivo, autor y caducidad opcional.
- SDK `data_access`: filtra por dependencia sin herencia ni bypass de datos para
  managers. Admin restringido a superusuarios vigentes, sin borrado de excepciones.
- Integración y límites en `docs/apps/data-access.md`. El SDK no se aplica solo a
  todas las consultas: la adopción por apps/consumidores es obligatoria y pendiente
  para expedientes, API y archivos municipales que todavía no están implementados.
- Migración probada en base de tests; no aplicada a la base real.
- Validación actual: **64 pruebas pasan**, con 15 pruebas nuevas de alcance y
  gestión de excepciones. Cubren IDs ajenos (404), exportación filtrada, jerarquía
  sin herencia, grants por operación, revocación/caducidad, cambios de adscripción,
  bajas, membresías suspendidas, módulos desactivados, managers sin bypass y
  gestión en Admin con registro de otorgante y bitácora.
- `makemigrations --check --dry-run`: sin cambios pendientes fuera de 0010.

## Seguimiento OpenProject — épica OP#37

- OP#38: `feature/OP-38-identidad-password-correo`, identidad/TOTP/correo. 83 pruebas
  pasan; evidencia y cuerpo de PR en `docs/reviews/OP-38.md`.
- OP#39: `feature/OP-39-sesiones-panel-revocacion`, panel, IP/dispositivo y revocación.
- OP#40: `feature/OP-40-privilegios-sudo-reauth`, separación de autoridad y SUDO.

Trabajar con ramas apiladas en ese orden por dependencias; todos los commits citan
subtarea y OP#37. Las tres ramas se publicaron con autorización; no hay PR publicado. Mantener cuerpos locales con
`Closes OP#38`, `Closes OP#39` y `Closes OP#40` y evidencia de suite acumulada.

### OP#39 — sesiones implementadas

Panel personal paginado, IP/navegador, revocación individual y total, comprobación
de contraseña, CSRF y auditoría. Middleware rechaza registros revocados o ausentes
sin restaurarlos; rotaciones conservan la sesión actual. Migración 0012 pendiente
en BD real. Suite acumulada: **95 pruebas pasan**. Evidencia en `docs/reviews/OP-39.md`.

### OP#40 — privilegios y SUDO implementados

Bypass técnico limitado a Seguridad/Configuración; membresías/permisos explícitos
en funciones y capacidades departamentales. SUDO por sesión de 300 segundos,
contraseña y nuevo TOTP, protección de POST administrativo/HTMX y auditoría.
Roles funcionales owner/admin requieren MFA. Cambiar flags administrativos invalida
sesiones. UserAdmin restringe edición de cuentas al superusuario para evitar elevación.

Suite acumulada: **120 pruebas pasan** (64 iniciales + 56 nuevas). Evidencia de las
subtareas en `docs/reviews/OP-38.md`, `OP-39.md` y `OP-40.md`, con sintaxis de cierre.
Las tres ramas están publicadas y apiladas; no hay PR publicado.

Pendiente operativo de fase 3: aplicar migraciones 0011–0013 y django-otp al entorno
destino, revisar roles históricos, probar SMTP real y ensayar recuperación con la
institución. El contrato de futura identidad ciudadana usa UUID y perfil separado
del laboral; no se construye un registro ciudadano en estas tres subtareas.


### Fase 4 — implementación inicial

Rama feature/core-hardening-phase-4 sobre OP#40 por dependencia, sin merge ni push.
IDs de seguimiento de fase 4 todavía no confirmados; no reutilizar OP#37 para ella.

- Auditor deja de silenciar errores y no confía directamente en X-Forwarded-For.
- Correlación por petición, actor de sistema, redacción estructurada y eventos sin edición por save/Admin.
- Transacción HTTP revierte cambio si falla evidencia; fallo simulado cubierto.
- Antes/después en grants y disponibilidad de módulos; normalización completa de eventos heredados pendiente.
- Monitoreo BD/caché mediante comando con JSON y salida no cero ante fallos.
- Backup/verify/restore para SQLite/PostgreSQL y media, destinos nuevos, SHA256.
- Simulacro aislado SQLite con expediente/archivo restaurados y pruebas negativas.

No se aplicó 0014 a la BD real. Cierre operativo pendiente: PostgreSQL real, copia
externa protegida, alertas conectadas, retención institucional, RPO/RTO y ensayo
integral medido. Límites y procedimiento en docs/deployment/audit-continuity.md.

Evidencia local de fase 4: **136 pruebas pasan** (120 previas + 11 auditoría/monitoreo
+ 5 continuidad). Django check, migraciones sin cambios pendientes, Tailwind y
collectstatic pasan. No se ejecutaron herramientas PostgreSQL contra un servidor.
