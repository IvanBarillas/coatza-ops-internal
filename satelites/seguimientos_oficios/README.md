# Seguimiento de Oficios

App satélite propia (no toca el Core). Registra oficios y documentos recibidos y enviados,
con folio consecutivo, estados, adjuntos PDF, OCR y búsqueda. Contexto de diseño y reglas de
agnosticismo: `AGENTS.md` (sección "Apps satélite propias").

## Activación

```env
AXENTRA_EXTRA_APPS=satelites.seguimientos_oficios
```

Después: `migrate`, `check_axentra_modules --persist`, activar el módulo en el Hub y dar
membresía a los usuarios.

## Ajustes (entorno o `.env.<DJANGO_ENV>`)

| Variable | Uso | Por defecto |
|---|---|---|
| `OFICIOS_ARCHIVOS_ROOT` | Almacén de PDF adjuntos, por contenido (`AAAA/MM/xx/<sha256>.pdf`) | `MEDIA_ROOT/oficios` |
| `OFICIOS_BANDEJA_RAIZ` | Raíz donde está montada la QNAP; las carpetas por dirección son relativas a ella | vacío (la bandeja no funciona) |
| `OFICIOS_OCR_COMANDO` | Ejecutable de OCR | `ocrmypdf` |
| `OFICIOS_OCR_IDIOMA` | Idioma de Tesseract | `spa` |
| `OFICIOS_OCR_TIMEOUT` | Segundos máximos por documento | `900` |

`OFICIOS_ARCHIVOS_ROOT` debe estar en un volumen persistente y con respaldo.

## Bandeja de la QNAP (SMB)

La app no guarda credenciales SMB: el servidor monta el recurso y la app lee la carpeta.

```
# /etc/oficios-qnap.cred   (chmod 600, dueño root)
username=USUARIO
password=CONTRASEÑA
domain=DOMINIO
```

```
# /etc/fstab   (requiere cifs-utils)
//172.16.2.5/documentos  /mnt/qnap  cifs  credentials=/etc/oficios-qnap.cred,uid=<usuario-del-servicio>,gid=<grupo>,file_mode=0660,dir_mode=0770,vers=3.0,_netdev,nofail,x-systemd.automount  0 0
```

Recurso público: sustituir `credentials=...` por `guest`. Si cada departamento tiene su propio
recurso o credencial, montar cada uno en una subcarpeta de la raíz (`/mnt/qnap/innovacion`, …)
con su archivo de credenciales.

Luego `OFICIOS_BANDEJA_RAIZ=/mnt/qnap` y, en la pantalla **Configuración** del módulo, indicar por
dirección las carpetas de recibidos y de evidencias (relativas a la raíz). La cuenta SMB necesita
escritura: al adjuntar, el archivo se mueve a `procesados/AAAA-MM/`; con solo lectura el adjunto
funciona pero el archivo sigue apareciendo en la lista. En contenedores, montar la raíz con el
mismo permiso de escritura en `web`.

## Despliegue (Podman)

`deploy/oficios/` contiene lo propio de este repo (no se toca el Dockerfile ni el compose del Core):

- `Containerfile`: capa con `ocrmypdf` y `tesseract-ocr-spa` sobre la imagen base. Verificado: se construye
  y `ocrmypdf --language spa --force-ocr --sidecar` extrae el texto de un PDF de prueba dentro del contenedor.
- `build.sh`: construye la base y la capa de OCR (`localhost/axentra-ops-internal:latest`).
- `docker-compose.oficios.yml`: override de `docker-compose.prod.yml` (misma imagen para `web` y `worker`, el
  worker monta el mismo volumen `media_data` para leer los PDF, `web` monta la QNAP). **No se ha levantado
  con `.env.prod` real**: revisarlo antes de usarlo.

Pendiente de resolver en el servidor real: el usuario del contenedor (`axentra`, UID 1000) debe poder
**escribir** en la QNAP montada. En Podman rootless eso depende del mapeo de UID (por ejemplo `userns: keep-id`
o montar el CIFS con `uid=`/`gid=` del UID que ve el contenedor). Sin escritura el adjuntar funciona, pero el
archivo no se mueve a `procesados/`. Además, `media_data` guarda los PDF adjuntos: incluirlo en los respaldos.

## OCR

Requiere `ocrmypdf` y `tesseract` con el idioma español en el proceso que ejecuta la cola
(`qcluster`), no en `web`. La imagen del worker del Core no los incluye: hace falta una imagen
propia para el worker. Sin ellos los adjuntos quedan con OCR en estado Error y se reintentan con:

```bash
python manage.py oficios_reprocesar_ocr
```

El PDF original nunca se modifica; solo se guarda el texto extraído, con un salto de página (`\f`) entre hojas,
y una copia normalizada (minúsculas, sin acentos, misma longitud) sobre la que se busca. PostgreSQL usa texto
completo en español con índice GIN sobre esa copia; SQLite, coincidencia por subcadena.

**Búsqueda en documentos** (menú *Búsqueda*): lista los documentos que contienen la consulta en sus datos o en el
OCR, sin importar acentos ni mayúsculas, con la página y un fragmento resaltado. Al elegir un resultado, el PDF se
abre a la derecha en esa página (iframe del visor del navegador: `#page=N` funciona en todos; el resaltado de la
palabra lo aplica el visor de Firefox, no el de Chrome). Los PDF nuevos aparecen cuando termina su OCR.

## Importar histórico ya digitalizado

Comando: `oficios_importar_historico --direccion <slug|nombre> --carpeta <ruta relativa a la raíz de la bandeja>`.
Sin `--aplicar` solo simula y reporta; con `--aplicar` escribe. No mueve ni borra los PDF de la QNAP.

- `--sentido recibido|enviado` y `--clase` fijan los valores para todos los archivos.
- `--csv manifiesto.csv` (columnas `archivo,sentido,clase,fecha,folio,contraparte,asunto,director`; solo
  `archivo` es obligatoria) permite datos por archivo. Con CSV solo se importan los archivos listados.
- Sin CSV: la fecha sale del nombre (`AAAA-MM-DD ...`) o de la fecha del archivo, el asunto del nombre, y en los
  enviados el folio se busca en el nombre (`IN-045-2025 ...` equivale a `IN-045/2025`). Un enviado sin folio se
  reporta como error.
- Enviados importados quedan **Concluidos** (el PDF es la evidencia); recibidos, **Registrados**. El director
  queda vacío salvo que venga en el CSV: nunca se usa el titular actual, porque falsearía el histórico.
- El contador de folios avanza hasta el mayor importado, así el siguiente folio generado continúa la serie.
- Es idempotente: un PDF con el mismo contenido ya registrado en esa dirección se omite.
- El OCR no se encola en bloque; al terminar, `oficios_reprocesar_ocr` lo procesa.

## Reglas de negocio

- El folio de los enviados sale de la **Nomenclatura** (dirección + clase), con contador por año.
  Se administra en el admin de Django hasta que exista su pantalla.
- Estados: Generado → Entregado → Concluido (con evidencia PDF); Cancelado desde cualquiera, con
  motivo. Cancelar un Concluido exige `can_cancel_concluded`. Los documentos no se eliminan.
- Director, dirección, folio (en enviados), clase y sentido quedan congelados al registrar; el historial es
  solo de escritura.
- Seguimiento: la lista abre en **Pendientes** (enviados Generado o Entregado, del más antiguo al más nuevo,
  con los días transcurridos desde la entrega o el registro); las demás pestañas son Concluidos (incluye los
  recibidos registrados), Cancelados y Todos. Buscar texto sin elegir pestaña busca en Todos. Sobre los pendientes
  se ve el resumen por gestor y se puede filtrar por gestor o por "sin gestor".
- Gestor: quien lleva el oficio a la dependencia y trae la evidencia. Es un catálogo por dirección (en Catálogos),
  solo aplica a enviados, se asigna al registrar y se reasigna al editar, con rastro en el historial.
  Un gestor puede vincularse (opcional) a un usuario con membresía en el módulo; ese usuario ve sus pendientes
  (Generado o Entregado) en **Mis pendientes**. El rol `gestor` solo tiene `has_access_module` y
  `can_view_own_pendings`: no ve la lista general ni puede ejecutar acciones; sí abre el detalle y los archivos
  de sus propios pendientes. Al concluir o cancelar un documento deja de verlo.
- Editar (`can_edit_oficio`): asunto, remitente o destinatario y fecha (en enviados, dentro del año del
  folio); en recibidos también el folio del remitente. Un cancelado no se edita. Cada cambio guarda el valor
  anterior, el nuevo, quién y el motivo opcional.
