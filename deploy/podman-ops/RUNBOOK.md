# Runbook — Core + satélites en `podman-ops01` (entorno semi real DEV)

Lo ejecuta **el usuario**, en `podman-ops01`, con su usuario rootless (el mismo de los Quadlets de Hermes).
Convive con `hermes-tramites-app`/`hermes-tramites-db`/`hermes-api`, que **no se tocan** hasta el paso 10 (opcional).
Todo lo que sigue se probó antes en una máquina de desarrollo (podman 5.8.7; el host tiene 5.8.2) con secretos de prueba;
lo que NO se pudo probar allí (Traefik, DNS, certificados, los archivos reales de Hermes) está marcado con **[no probado]**.

Contenido de esta carpeta: `Containerfile`, `build.sh`, `healthcheck.py`, `paridad_tramites.py`, `quadlet/` (units + `axentra-core.env`).

## Qué se despliega

| Pieza | Nombre | Notas |
|---|---|---|
| Web (Core + Trámites + Situaciones + Ciudadanía) | contenedor `axentra-core`, redes `frontend` + `axentra-core-net` | sirve **dos dominios** con la misma imagen |
| Worker de correo (Django-Q2) | `axentra-core-worker` | solo `axentra-core-net` |
| PostgreSQL 16 normal (los satélites no usan GIS) | `axentra-core-db`, volumen `axentra-core-db` | NUEVA y separada de `hermes-tramites-db`; solo en la red interna `axentra-core-net`, sin puertos |
| Dominio del personal | `digital-dev.axentra.com.mx` | Hub, directorio, dashboards. **La API no sale por Traefik** (`!PathPrefix(/api/)`) |
| Dominio del ciudadano | `ciudadano-dev.axentra.com.mx` | directorio, `/tramites/`, `/situaciones/`, `/ciudadano/` (una sola sesión) |
| API para Hermes | `http://axentra-core:8000/api/v1/...` por la red `frontend` | http interno, exento de la redirección a HTTPS solo bajo `^api/v1/` |

Espejo Redis de Trámites: **apagado** (no se define `TRAMITES_REDIS_URL`).

## 0. Antes de empezar

1. DNS (los creas tú): `digital-dev.axentra.com.mx` y `ciudadano-dev.axentra.com.mx` hacia el Traefik del host.
2. Comprobar que nada choca:
   ```bash
   podman ps -a --format '{{.Names}}' | grep -E '^axentra-core' || echo "libre"
   podman volume ls --format '{{.Name}}' | grep -E '^axentra-core' || echo "libre"
   podman network ls --format '{{.Name}}' | grep -E '^axentra-core' || echo "libre"
   podman secret ls --format '{{.Name}}' | grep -E '^axentra_core_' || echo "libre"
   ```

## 1. Código (4 repos hermanos en `~/axentra`)

```bash
mkdir -p ~/axentra && cd ~/axentra
git clone git@github.com:IvanBarillas/axentra-core-django.git          axentra-core-django
git clone git@github.com:IvanBarillas/axentra-mod-tramites.git         axentra-mod-tramites
git clone git@github.com:IvanBarillas/axentra-mod-situaciones-vida.git axentra-mod-situaciones-de-vida
git clone git@github.com:IvanBarillas/axentra-ciudadania.git           ciudadania
```
(Los nombres de carpeta importan: `build.sh` los espera así. Para actualizar más tarde: `git -C <carpeta> pull --ff-only`.)

## 2. Construir la imagen

```bash
cd ~/axentra/axentra-core-django
./deploy/podman-ops/build.sh dev            # ~1-3 min; imprime la referencia y el commit de cada repo
podman image inspect localhost/axentra-core:dev --format '{{index .Labels "mx.axentra.versiones"}}'
```
Usa `git archive` de `main` de cada repo (solo archivos versionados: ningún `.env`, `.venv` ni base local entra a la imagen).
Otra rama: `REF_CORE=... REF_TRAMITES=... ./deploy/podman-ops/build.sh dev`. Las versiones exactas de las dependencias de los
satélites quedan dentro de la imagen: `podman run --rm --entrypoint cat localhost/axentra-core:dev /app/requirements-imagen.txt`.

## 3. Secretos (nunca en archivos)

Los valores se generan y se pasan por tubería: no se imprimen ni quedan en el historial.

```bash
# contraseña de la BD y la URL que la contiene (deben coincidir)
PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24), end="")')"
printf %s "$PW" | podman secret create axentra_core_db_password -
printf %s "postgresql://axentra:${PW}@axentra-core-db:5432/axentra" | podman secret create axentra_core_database_url -
unset PW
# SECRET_KEY de Django
python3 -c 'import secrets; print(secrets.token_urlsafe(50), end="")' | podman secret create axentra_core_secret_key -
# contraseña inicial del propietario (te la pide sin mostrarla; elige una robusta: se le pedirá cambiarla en el primer acceso)
read -rs -p "Contraseña inicial del propietario: " OWNER_PW; echo
printf %s "$OWNER_PW" | podman secret create axentra_core_owner_password -; unset OWNER_PW
```

**Llave de la API** (`INTERNAL_API_KEY`; la que Hermes envía en `X-API-Key`). Elige UNA:

- **A (recomendada): la MISMA que ya usa la app original.** Así, si más adelante conmutas Hermes, solo cambia su `BaseUrl` y
  revertir es cambiar una línea. Mira el nombre en `podman secret ls` (los de Hermes/Trámites) y copia su valor sin mostrarlo:
  ```bash
  ORIG_SECRET="<nombre-del-secreto-de-la-llave-de-tramites>"
  printf %s "$(podman secret inspect --showsecret --format '{{.SecretData}}' "$ORIG_SECRET")" | podman secret create axentra_core_internal_api_key -
  ```
- **B: una nueva:** `python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | podman secret create axentra_core_internal_api_key -`
  (entonces en el paso 10 hay que apuntar Hermes también a este secreto).

Verificar (solo nombres): `podman secret ls --format '{{.Name}}' | grep axentra_core_` → 5 secretos.

## 4. Instalar y arrancar los units

```bash
mkdir -p ~/.config/containers/systemd ~/.config/axentra-core
cp ~/axentra/axentra-core-django/deploy/podman-ops/quadlet/*.container \
   ~/axentra/axentra-core-django/deploy/podman-ops/quadlet/*.volume \
   ~/axentra/axentra-core-django/deploy/podman-ops/quadlet/*.network  ~/.config/containers/systemd/
cp ~/axentra/axentra-core-django/deploy/podman-ops/quadlet/axentra-core.env ~/.config/axentra-core/axentra-core.env
systemctl --user daemon-reload
systemctl --user start axentra-core-db axentra-core axentra-core-worker
sleep 40; podman ps --format '{{.Names}} {{.Status}}' | grep axentra-core
```
Esperado: `axentra-core-db ... (healthy)`, `axentra-core ... (healthy)`, `axentra-core-worker Up`.
Si `daemon-reload` no genera los units, revisa con `/usr/libexec/podman/quadlet -dryrun -user`.
Los units llevan `[Install] WantedBy=default.target` (arrancan con el usuario; requiere `loginctl enable-linger`, que ya usan los de Hermes).

## 5. Migrar y cargar el catálogo (102 trámites)

```bash
X="podman exec axentra-core python manage.py"
$X check                                   # sin errores (los avisos axentra.W002 del worker/bootstrap son esperados: no usan la API)
$X migrate --noinput
for c in 1_seed_sedes 2_seed_dependencias 3_seed_categorias 4_seed_guias 5_seed_tramites; do $X $c | tail -1; done
$X check_axentra_modules --persist
podman exec axentra-core-db psql -U axentra -d axentra -tc "select count(*) from portal_tramite"     # 102
```
Los comandos van **numerados** y en ese orden (`seed_catalogos` está roto: problema conocido, no se usa). Los datos salen del
paquete (`catalogo_coatza.json`), no de la BD de `hermes-tramites-db`. Con `costo_variable` el `costo` queda en 0 y la regla en
`costo_texto` (ver «Costos» abajo). Repetir `5_seed_tramites` es seguro (idempotente).

## 6. Propietario inicial

```bash
podman run --rm --network axentra-core-net --env-file ~/.config/axentra-core/axentra-core.env \
  --secret axentra_core_secret_key,type=env,target=SECRET_KEY \
  --secret axentra_core_database_url,type=env,target=DATABASE_URL \
  --secret axentra_core_owner_password,type=env,target=AXENTRA_OWNER_DEFAULT_PASSWORD \
  localhost/axentra-core:dev python manage.py bootstrap_axentra_owner
```
(La contraseña solo existe en este contenedor efímero, no en `axentra-core`.) Sin SMTP en DEV el correo de verificación no sale:
marca el del propietario como verificado a mano (la política `AXENTRA_REQUIRE_VERIFIED_EMAIL` sigue activa para todos los demás):
```bash
podman exec axentra-core python manage.py shell -c "
from django.contrib.auth import get_user_model as g
u = g().objects.get(email='owner@axentra.com.mx'); u.is_email_verified = True; u.save(update_fields=['is_email_verified'])"
```
El propietario debe cambiar la contraseña y enrolar MFA (TOTP) en su primer inicio de sesión (obligatorio para cuentas administrativas).

**Paleta institucional.** Una instalación nueva arranca con la paleta de marca de Axentra (`apps/shared/branding.py`: tinta oscura, gris frío y acento esmeralda).
Al aprovisionar, el propietario define la paleta del cliente en Configuración → Entidad Institucional; el botón «Restaurar Axentra» vuelve a la base
y «Deshacer cambios» a lo último guardado.

## 7. Activar los satélites

Trámites y Situaciones nacen **desactivados** (`default_enabled=False`); hasta activarlos no salen en el directorio público.
Por el Hub (recomendado) **[no probado en navegador]**: `https://digital-dev.axentra.com.mx/` → iniciar sesión como propietario → centro de
módulos → activar **Trámites** y **Situaciones de Vida**. Alternativa sin navegador (usa el mismo servicio auditado; probada):
```bash
podman exec axentra-core python manage.py shell -c "
from django.contrib.auth import get_user_model as g
from apps.shared.module_sdk.services import set_module_enabled as s
u = g().objects.get(email='owner@axentra.com.mx')
for c in ('tramites', 'situaciones_de_vida'): print(c, s(code=c, enabled=True, actor=u).is_active)"
```
Ciudadanía no tiene panel ni interruptor en el Hub (su interruptor es `CIUDADANIA_HABILITADA`).

## 8. Verificar

```bash
# a) por Traefik [no probado]: dominios, certificado y redirección
curl -sI https://digital-dev.axentra.com.mx/            | head -1     # 200
curl -sI https://digital-dev.axentra.com.mx/directorio/ | head -1     # 200
curl -s  https://ciudadano-dev.axentra.com.mx/ | grep -oE 'href="https://ciudadano-dev[^"]+"' | sort -u   # 3 tarjetas: /tramites/catalogo/, /situaciones/, /ciudadano/cuenta/
curl -sI https://ciudadano-dev.axentra.com.mx/tramites/catalogo/ | head -1   # 200
curl -s -o /dev/null -w '%{http_code}\n' https://ciudadano-dev.axentra.com.mx/app/                # 404: el dominio público no tiene el panel
curl -s -o /dev/null -w '%{http_code}\n' https://digital-dev.axentra.com.mx/api/v1/tramites/buscar # 404 de Traefik: la API no sale por aquí

# b) la API por la red interna (como la llamará Hermes): sin llave 401
podman run --rm --network frontend --entrypoint python localhost/axentra-core:dev -c "
import urllib.request, urllib.error
try: urllib.request.urlopen('http://axentra-core:8000/api/v1/tramites/buscar')
except urllib.error.HTTPError as e: print('sin llave ->', e.code)"

# c) el ciudadano: /ciudadano/registro/ (el correo no sale sin SMTP: para probar el flujo completo crea un ciudadano de prueba)
podman exec axentra-core python manage.py shell -c "
from ciudadania.services import registrar_ciudadano, generar_token_verificacion, verificar_email
c = registrar_ciudadano(email='ciudadano.prueba@example.invalid', password='CAMBIA-ESTA-2026!', nombre_completo='Persona de Prueba')
verificar_email(generar_token_verificacion(c))"
```
Con esa cuenta, en `https://ciudadano-dev.axentra.com.mx/ciudadano/login/`: el saludo aparece también en `/tramites/` y `/situaciones/`
(una sola sesión). Bórrala al terminar (`Ciudadano.objects.filter(email=...).delete()` en `manage.py shell`).

## 9. Paridad original vs satélite (solo lectura)

```bash
ORIG_SECRET="<nombre-del-secreto-de-la-llave-de-tramites>"     # el mismo del paso 3
podman run --rm -i --network frontend --entrypoint python \
  -e ORIGINAL_URL=http://hermes-tramites-app:8000 -e SATELITE_URL=http://axentra-core:8000 \
  --secret "$ORIG_SECRET",type=env,target=ORIGINAL_API_KEY \
  --secret axentra_core_internal_api_key,type=env,target=SATELITE_API_KEY \
  localhost/axentra-core:dev - < ~/axentra/axentra-core-django/deploy/podman-ops/paridad_tramites.py
```
Hace ~110 consultas GET a cada una. Sale con código 0 si todas las diferencias son las esperadas:
- **acentos**: el satélite normaliza acentos al buscar; el original prefiltra con `icontains` que los distingue (el satélite
  devuelve más, nunca menos);
- **costo**: hasta 15 trámites con `costo` ≠ 0 en el original quedan en 0 en el satélite (el seeder ya no inventa el precio; ver «Costos»;
  la salida lista los que alcanzan las consultas);
- **orden-requisitos**: `requisitos` no tiene orden definido en el modelo; se compara el conjunto;
- los `id` son de cada base (se empareja por título).
Cualquier otra diferencia se imprime como «DIFERENCIAS INESPERADAS» y el código de salida es 1.
Si el original de este host usa otra clave o la de los dos no coincide, la comprobación previa lo dice (401/400/redirección).
Con `--json /ruta` (dentro del contenedor, p. ej. montando `-v ~/paridad:/out:Z` y `--json /out/paridad.json`) guarda el detalle sin claves.

## 10. OPCIONAL, solo DEV y reversible: apuntar Hermes al satélite [no probado]

No lo hagas hasta que el paso 9 salga bien. **No se cambia `hermes-api`; se cambia su configuración en el host**, por el usuario.
```bash
cd ~/.config/containers/systemd
cp hermes-api.container hermes-api.container.antes-del-satelite          # respaldo (fuera de la extensión .container)
grep -n 'MunicipalApis__Tramites' hermes-api.container                   # ver las líneas exactas (BaseUrl y la llave)
```
Cambia solo la línea del `BaseUrl` de `http://hermes-tramites-app:8000/` a `http://axentra-core:8000/`. Si en el paso 3 elegiste la
opción **A**, la llave no cambia. Con la **B**, cambia también el `Secret=` de la llave a `axentra_core_internal_api_key`.
Mueve el respaldo fuera de la carpeta antes de recargar (Quadlet lee todo `*.container`):
```bash
mv hermes-api.container.antes-del-satelite ~/hermes-api.container.antes-del-satelite
systemctl --user daemon-reload && systemctl --user restart hermes-api
podman logs --tail 20 hermes-api
```
Prueba una pregunta de trámites por el canal habitual y mira `podman logs axentra-core` (peticiones `GET /api/v1/tramites/buscar` con 200).
**Revertir:** `cp ~/hermes-api.container.antes-del-satelite ~/.config/containers/systemd/hermes-api.container && systemctl --user daemon-reload && systemctl --user restart hermes-api`.

## 11. Revertir todo (deja el host como estaba)

```bash
systemctl --user stop axentra-core axentra-core-worker axentra-core-db
rm ~/.config/containers/systemd/axentra-core*.{container,volume,network}
rm -r ~/.config/axentra-core
systemctl --user daemon-reload
# irreversible: borra la base y los archivos subidos del Core
podman volume rm axentra-core-db axentra-core-media axentra-core-logs
podman network rm axentra-core-net
for s in db_password database_url secret_key internal_api_key owner_password; do podman secret rm axentra_core_$s; done
podman rmi localhost/axentra-core:dev
```
`hermes-tramites-app`, `hermes-tramites-db` y `hermes-api` (si no hiciste el paso 10) no se tocaron en ningún momento.

## Costos (nota, sin corregir datos)

En el catálogo original 15 trámites con `costo_variable` traían en `costo` un número que **no es un precio** (`201.0` y `136.0`,
números de artículo del Código Hacendario; `198.0`; `29.0`, el día de «29 de diciembre de 2022»; `1.82`/`15.52`, unidades de UMA
por metro lineal…). El origen era el seeder (`5_seed_tramites`: tomaba el primer número de `costo_texto`). En el satélite ese número
ya no se inventa: `costo` = 0 y el importe o la regla están en `costo_texto`. El JSON del catálogo no se modificó y las bases ya
sembradas con la lógica anterior se corrigen volviendo a correr `5_seed_tramites`. El original NO se corrige (no se toca): la
paridad mostrará esas diferencias como «esperadas».

## Problemas conocidos

- `seed_catalogos` no funciona (llama a `seed_sedes`… que no existen): usar los comandos numerados.
- `requisitos` de la API no tiene orden definido en el modelo (`Requisito` sin `Meta.ordering`): el orden puede variar entre bases y
  tras volver a sembrar. La paridad lo trata como esperado; conviene fijar un orden en el satélite (pendiente para su mantenedor).
- El aviso `axentra.W002` (API sin llave) aparece en el worker y en el bootstrap: no usan la API.
- Django solo escribe en `/app/logs/production_django.log` a nivel WARNING; `podman logs axentra-core` muestra gunicorn.
- El correo real no sale (sin SMTP en DEV); el propietario se marca verificado a mano (paso 6).
- Los archivos subidos (`/media/`) no se sirven en producción (Django con `DEBUG=False`): formatos y fotos subidos desde el dashboard
  necesitan que el proxy los sirva. El catálogo sembrado usa URLs externas y no lo necesita.
- Si un satélite se actualiza antes que el Core, su manifiesto fallará (`api_urlconf`/`public_urlconf` desconocidos): actualiza el Core primero.
