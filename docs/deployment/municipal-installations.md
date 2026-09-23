# Una instalación por ayuntamiento

Decisión del propietario: cada ayuntamiento dispone de su propia instalación y
base de datos. No alojamos instituciones distintas en tablas compartidas. El mismo
repositorio/imagen se puede distribuir a varios ayuntamientos.

## Recursos separados

Por instalación: base y credenciales PostgreSQL, SECRET_KEY, dominio HTTPS,
ALLOWED_HOSTS, configuración institucional, volúmenes de media y logs, archivos de
entorno y respaldos. Si se usa Redis o una cola, provisionar recursos y permisos
separados; un prefijo de claves no es una frontera de seguridad.

No compartir cookies mediante SESSION_COOKIE_DOMAIN entre ayuntamientos. Los
valores por defecto de Django mantienen cookies por host. No compartir el mismo
hostname entre municipios cambiando únicamente el puerto: las cookies no se aíslan
por puerto. Los ciudadanos y funcionarios existen en la BD de su instalación.

## Varias instalaciones en un servidor

Usar directorios de despliegue distintos y nombres de proyecto Compose únicos.
Los volúmenes/redes del compose no tienen `name` global, por lo que el nombre del
proyecto separa sus recursos. No reutilizar `-p` entre municipios.

Ejemplo desde el directorio del municipio A:

```bash
podman-compose --env-file .env.prod -p axentra-municipio-a -f docker-compose.prod.yml up --build -d
```

Para otro municipio: otro directorio/.env.prod, `-p axentra-municipio-b` y otro
AXENTRA_HTTP_PORT, por ejemplo 8001. Los secretos deben ser distintos incluso si
los nombres internos de DB/usuario coinciden en contenedores separados.

Preparar `.env.prod` desde `.env.example`, cambiando al menos:

- `DJANGO_ENV=prod`, `DJANGO_SETTINGS_MODULE=core.settings.production`.
- SECRET_KEY, POSTGRES_PASSWORD y DATABASE_URL coherentes entre sí.
- ALLOWED_HOSTS con el dominio de esta institución, sin wildcard.
- CSRF_TRUSTED_ORIGINS con orígenes HTTPS completos cuando sean necesarios;
  producción lee esta variable y no confía en un dominio fijo de Axentra.
- SMTP y remitente; credenciales iniciales de operación según procedimiento.

Compose lee las variables de interpolación mediante `--env-file`; el `env_file`
del servicio únicamente inyecta valores al contenedor. AXENTRA_HTTP_PORT no cambia
el puerto interno (8000). La publicación predeterminada queda en 127.0.0.1 para un
proxy HTTPS en el host. Si el proxy vive en otro contenedor, conectarlo a la red
correspondiente o definir una dirección de enlace accesible deliberadamente.
No dar por sentado que el loopback del host es el de un contenedor.

El proxy dirige cada dominio únicamente al backend de su municipio. La BD no se
publica al host. Esto no sustituye políticas de acceso del servidor ni evita que
un administrador del host pueda acceder a los recursos de varias instalaciones.

## Verificación de despliegue

Antes de operar, comprobar con credenciales de prueba que el dominio A responde
con la identidad A y el dominio B con B; revisar los nombres de proyectos,
volúmenes y destinos de DB. Verificar que las credenciales de una instancia no
abren las bases de otras. Ensayar restauración en recursos separados, nunca sobre
la base activa. No se han aprovisionado instalaciones reales con esta modificación.

Los permisos entre dependencias dentro del ayuntamiento son otra capa. El gate de
módulo no filtra automáticamente expedientes ni archivos; cada consumidor debe
aplicar el alcance de datos definido para su operación.

## Paleta institucional

Los colores por defecto (primario, secundario y acento) están en `apps/shared/branding.py` y son la identidad de marca de Axentra
(tinta oscura, gris frío y acento esmeralda), no la de una institución. Cada ayuntamiento define su paleta al desplegar, en Configuración → Entidad Institucional. Cambiar
`DEFAULT_BRAND_COLORS` solo afecta instalaciones nuevas y al botón «Restaurar Axentra»; las ya configuradas conservan lo guardado.
