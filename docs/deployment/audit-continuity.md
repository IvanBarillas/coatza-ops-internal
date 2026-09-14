# Fase 4 — Auditoría y continuidad municipal

## Evidencia y atomicidad

Aplicar `0014_audit_correlation_system_actor` antes de iniciar la nueva versión.
Cada petición recibe un UUID generado en el servidor (`X-Request-ID`); los eventos
creados por ella comparten correlación. No se confía en un ID aportado por clientes.
Los eventos históricos conservan correlación nula. Un trabajo sin usuario debe
identificarse con `system_actor`; no crear cuentas humanas ficticias para tareas.

El auditor deja de ocultar fallos. En solicitudes HTTP de escritura, la base default
agrupa cambio, auditoría y sesión en una transacción. Si falla la persistencia de
un evento, se devuelve 503 y se revierte aunque una vista antigua capture el error.
Los fallos 500 también revierten. Los 400/403 no borran automáticamente evidencias
ni contadores de intentos fallidos (axes/TOTP). Los servicios fuera de HTTP deben
usar su propia transaction.atomic alrededor de cambio y evidencia y propagar errores.

Este contrato no revierte archivos, correo, llamadas remotas ni datos de otras bases.
Las cargas pueden dejar archivos huérfanos si falla el guardado; no publicar archivos
privados sin autorización de su registro. Tareas y efectos externos confiables son
parte de fase 6. No escribir datos desde respuestas streaming ni desde GET.

Operaciones con evidencia obligatoria: asignación/revocación de accesos, permisos,
capacidad departamental, disponibilidad de módulos, configuración institucional y
acciones administrativas de identidad. La cobertura previa de eventos se conserva;
el middleware garantiza atomicidad cuando se escribe evidencia, no detecta una
vista que olvidó llamar al auditor. Cada nuevo consumidor debe probar ese requisito.

Grants entre dependencias y disponibilidad de módulos incluyen antes/después.
`audit_snapshots.snapshot` toma únicamente campos explícitos, no expedientes completos.
Otros eventos heredados conservan sus payloads: su normalización progresiva sigue
pendiente. Se redactan claves de contraseñas/tokens/secretos en estructuras anidadas;
esto no detecta secretos pegados en texto libre. No pasar cuerpos POST, cabeceras,
cookies, archivos o credenciales a las descripciones ni payloads.

La IP del auditor usa REMOTE_ADDR. No se acepta X-Forwarded-For sin una política de
proxy validada. Con proxy puede verse su IP; no usarla como identidad del ciudadano.

## Protección, acceso y conservación

Django Admin permite consultar según permisos, pero no añadir/editar/borrar eventos.
Guardar de nuevo un evento existente con Model.save se rechaza. Esto NO constituye
inmutabilidad: QuerySet.update/delete, bulk_create, SQL o el propietario de la BD
pueden omitir protecciones de aplicación. No usar esas rutas para cambiar evidencia.
Los superusuarios y operadores de infraestructura siguen siendo una frontera de
confianza. El almacenamiento externo con retención protegida debe configurarse y
ensayarse en el despliegue; todavía no hay sellado ni anclaje criptográfico externo.

No hay purga automática. Definir con la institución acceso, conservación y borrado
antes de programar retención. No elegir plazos legales genéricos para todos los
municipios. Restringir permisos Django de consulta/exportación de auditoría y
revisar delegaciones existentes del panel de Seguridad antes de abrirlo a operadores.

## Monitoreo

```bash
DJANGO_SETTINGS_MODULE=core.settings.production DJANGO_ENV=production \
  uv run python manage.py check_operational_health
```

Salida JSON con salud de BD/caché y código de salida no cero si falla. Solo realiza
SELECT 1 y una clave temporal propia de caché. No prueba SMTP, almacenamiento externo,
latencia de usuarios, replicación ni una caché compartida si se usa LocMemCache.
Configurar en el monitor institucional alertas por resultado no cero, HTTP 5xx,
`AUDIT_WRITE_FAILED`, falta de respaldos verificados y disco insuficiente. El comando
no envía alertas por sí mismo: destino y responsable siguen por acordar.

## Respaldos y restauración

`tools/continuity.py` respalda SQLite o PostgreSQL y media local. No lee .env ni incluye
secretos de configuración. PostgreSQL requiere pg_dump, createdb y pg_restore
compatibles con la versión del servidor. Credenciales por PG* o .pgpass; el argumento
database solo admite nombre simple, nunca contraseña/URI. Ejecutar con umask 077,
almacenamiento cifrado y destino privado de esa instalación.

Antes del respaldo, poner la instancia en mantenimiento y detener escritores,
workers y cargas. Una copia consistente de BD por sí sola no sincroniza media.
Los destinos deben ser nuevos y su directorio padre debe existir.

```bash
uv run python tools/continuity.py backup --engine postgresql \
  --database axentra_municipio --media /srv/municipio/media \
  --destination /backups/municipio/copia_nueva
uv run python tools/continuity.py verify /backups/municipio/copia_nueva
uv run python tools/continuity.py restore /backups/municipio/copia_nueva \
  --database axentra_ensayo_nuevo --destination /srv/ensayos/ensayo_nuevo
```

La restauración PostgreSQL crea una base NUEVA: si ya existe, falla. No usa --clean
ni reemplaza la base activa. Si falla, conservará un destino parcial para diagnóstico;
no conectar la aplicación a él. Restore no cambia settings ni activa servicios.
SQLite restaura database.sqlite3 dentro del destino nuevo, con comprobación de
integridad. Solo restaurar respaldos de procedencia confiable en entorno aislado:
un dump PostgreSQL ejecuta SQL y SHA256 no certifica autenticidad frente a alguien
que pueda modificar también el manifiesto.

Los hashes SHA256 comprueban inventario y contenido; enlaces simbólicos y archivos
adicionales se rechazan. No equivalen a cifrado, firma ni protección WORM. Copiar
respaldos verificados a una ubicación externa protegida por municipio, junto con
una custodia separada de secretos, configuración, versión del código y dependencias.
No se instala todavía un scheduler ni se purgan copias automáticamente.

## Simulacro y criterios pendientes

La suite crea una SQLite aislada con un expediente y un archivo de prueba, respalda,
verifica, restaura en un destino nuevo y compara folio y contenido. También comprueba
corrupción, inventario alterado, enlaces y rechazo de destinos existentes. No toca
la base de desarrollo ni representa un ensayo PostgreSQL de producción.

Antes de cerrar la fase operativa:

1. Acordar RPO (pérdida máxima tolerable), RTO (tiempo máximo para recuperar), frecuencia,
   retención y responsable. No hay valores institucionales confirmados aún.
2. Ejecutar el mismo ensayo con PostgreSQL, volumen representativo y permisos reales.
3. Arrancar una instancia aislada desde lo restaurado; comprobar login/TOTP, grants,
   archivos privados y flujos municipales. Desactivar envíos reales durante el ensayo.
4. Medir duración y fecha del punto recuperado; contrastarlas con RPO/RTO y registrar
   evidencia firmada por el responsable. Comprobar que llegan las alertas de fallo.
5. Solo después planificar la puesta en servicio; no marcar recuperación cumplida
   por tener un archivo de respaldo.
