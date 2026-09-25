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
| `OFICIOS_BANDEJA_RAIZ` | Carpeta base desde la que el comando `oficios_importar_historico` lee los PDF (solo importación; la subida normal usa el selector de archivos del navegador) | vacío |
| `OFICIOS_PRESTAMO_AVISO_DIAS` | Días para la fecha límite desde los que un préstamo aparece como *por vencer* | `3` |
| `OFICIOS_SEMAFORO_AMBAR` / `OFICIOS_SEMAFORO_ROJO` | Días pendientes desde los que un oficio pasa a ámbar y a rojo en el seguimiento | `7` / `15` |
| `OFICIOS_OCR_COMANDO` | Ejecutable de OCR | `ocrmypdf` |
| `OFICIOS_OCR_IDIOMA` | Idioma de Tesseract | `spa` |
| `OFICIOS_OCR_TIMEOUT` | Segundos máximos por documento | `900` |

`OFICIOS_ARCHIVOS_ROOT` debe estar en un volumen persistente y con respaldo.

## Subida de archivos

Los archivos se suben desde el navegador (selector de archivos del equipo del usuario, que puede navegar a
cualquier carpeta o unidad mapeada, sea QNAP, Samba o local). No hay carpetas de escaneo configuradas en el
servidor. Solo el importador del histórico (línea de comandos) lee una carpeta del servidor: si el histórico está
en un recurso de red, se monta en el servidor (`cifs-utils`, con un archivo de credenciales `chmod 600`, o `guest`
si es público) y se apunta `OFICIOS_BANDEJA_RAIZ` a esa carpeta.

## Despliegue (Podman)

`deploy/oficios/` contiene lo propio de este repo (no se toca el Dockerfile ni el compose del Core):

- `Containerfile`: capa con `ocrmypdf`, `tesseract-ocr-spa` y el static del satélite (visor PDF.js) sobre la imagen
  base. Verificado: la imagen se construye completa (base y capa), incluye el static con su manifiesto y `tesseract`
  con español, y `ocrmypdf --language spa --force-ocr --sidecar` extrae el texto de un PDF de prueba.
- `build.sh`: construye la base y la capa de OCR (`localhost/axentra-ops-internal:latest`).
- `docker-compose.oficios.yml`: override de `docker-compose.prod.yml` (misma imagen para `web` y `worker`, el
  worker monta el mismo volumen `media_data` para leer los PDF). **No se ha levantado
  con `.env.prod` real**: revisarlo antes de usarlo.

`media_data` guarda los PDF adjuntos: incluirlo en los respaldos.

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

**Visor de PDF.** Los resultados de la búsqueda abren el PDF en un visor propio basado en PDF.js (incluido en
`static/seguimientos_oficios/pdfjs/`, Apache-2.0; ver `PROCEDENCIA.md` para versión, hash y cómo actualizarlo, sin
CDN). Abre en la página encontrada, resalta las palabras buscadas (sin distinguir acentos ni mayúsculas) y tiene
contador y botones para saltar entre coincidencias; funciona igual en todos los navegadores. Un original escaneado es
solo imagen y no tiene texto que resaltar, así que el OCR conserva además una **copia con capa de texto**
(en la subcarpeta `ocr/` de la misma carpeta del original, con el mismo nombre) que usa solo el visor; la descarga y el archivo firmado siguen siendo el
original intacto. La copia se genera con `--skip-text`, que conserva las imágenes tal cual, y pesa casi lo mismo que el original (unos
KB más por la capa de texto), así que un PDF con OCR ocupa el doble en disco (original + copia). Solo si alguna
página ya traía texto digital se rehace con `--force-ocr`, que es más pesado. Para generar o aligerar las copias de
adjuntos ya procesados: `python manage.py oficios_reprocesar_ocr --buscables` (rehace las que faltan o pesan más
del doble que el original). La imagen de despliegue recolecta el static del
satélite (`deploy/oficios/Containerfile`).

**Orden del almacén:** `AAAA/<dirección>/<recibidos|enviados>/` contiene solo los originales; las copias con texto
del OCR viven en `AAAA/<dirección>/<recibidos|enviados>/ocr/`. Para entregar los originales (p. ej. en una auditoría)
basta copiar la carpeta sin la subcarpeta `ocr/`. Las copias se pueden regenerar en cualquier momento
(`oficios_reprocesar_ocr --buscables`), así que nunca son la única versión de nada.

**Alcance del OCR:** solo se procesan el **original** de los recibidos y el **documento firmado** de los enviados. La
**evidencia** (acuse) repite el firmado con el sello de recepción y no pasa por OCR. Los enviados importados del
histórico se guardan como firmado, así que sí se procesan y se pueden buscar.

**Búsqueda en documentos** (menú *Búsqueda*, con selector *Buscar en*: Todos, Recibidos o Enviados, y un panel plegable de filtros por clase, dirección y rango de fechas que se combinan con el texto): lista los documentos que contienen la consulta en sus datos o en el
OCR, sin importar acentos ni mayúsculas, con la página y un fragmento resaltado. Al elegir un resultado, el PDF se
abre a la derecha en esa página, con las palabras resaltadas (visor PDF.js propio, ver arriba). Los PDF nuevos
aparecen cuando termina su OCR.

## Importar histórico ya digitalizado

Comando: `oficios_importar_historico --direccion <slug|nombre> --carpeta <ruta relativa a OFICIOS_BANDEJA_RAIZ>`.
Sin `--aplicar` solo simula y reporta; con `--aplicar` escribe. No mueve ni borra los PDF de origen.

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

- Folio: cada dirección tiene el ajuste **Folio manual** (Catálogos), activo por defecto en esta fase. Con folio
  manual quien registra un enviado escribe el folio (obligatorio, único por dirección incluso frente a cancelados) y
  se puede corregir después con rastro en el historial; si sigue la nomenclatura, el contador avanza hasta ese
  número. Sin folio manual, el sistema lo genera. En los recibidos el folio del remitente siempre se captura a mano.
- El folio automático de los enviados sale de la **Nomenclatura** (dirección + clase), con contador por año.
  Se administra en el admin de Django hasta que exista su pantalla.
- Archivos por tipo: **Original** (recibidos), **Documento firmado** (enviados: el oficio ya firmado, se sube estando Generado; no cambia el estado) y **Evidencia de entrega** (enviados ya Entregados;
  concluye el documento). Estando Entregado o Concluido también se puede agregar un firmado.
- Estados: Generado → Entregado → Concluido (con evidencia PDF); Cancelado desde cualquiera, con
  motivo. Cancelar un Concluido exige `can_cancel_concluded`. Los documentos no se eliminan.
- Director, dirección, folio (en enviados), clase y sentido quedan congelados al registrar; el historial es
  solo de escritura.
- La lista de Documentos es compacta: Fecha, Folio (con clase y sentido debajo), Asunto (con remitente o destinatario
  debajo), Gestor y Estado; la Dirección solo aparece si el usuario ve más de una. Los días de espera y la categoría
  no van en la tabla (los días viven en Seguimiento; la categoría en el detalle y como filtro).
- Seguimiento: la lista abre en **Pendientes** (enviados Generado o Entregado, del más antiguo al más nuevo,
  con los días transcurridos desde la entrega o el registro); las demás pestañas son Concluidos (incluye los
  recibidos registrados), Cancelados y Todos. Buscar texto sin elegir pestaña busca en Todos. Sobre los pendientes
  se ve el resumen por gestor y se puede filtrar por gestor o por "sin gestor".
- Categoría: tema opcional (una por documento) con el que cada dirección clasifica sus documentos (p. ej. panteones,
  escuelas). Catálogo por dirección en Catálogos, elegible al registrar y al editar (con rastro en el historial),
  visible en lista, detalle y búsqueda, y filtrable en ambas. Las categorías no se borran: se desactivan, y un
  documento ya clasificado conserva la suya aunque se desactive.
- Gestor: quien lleva el oficio a la dependencia y trae la evidencia. Es siempre un **usuario existente** con
  membresía en el módulo: en Catálogos (por dirección) se elige el usuario y el nombre sale de su cuenta (si dos
  comparten nombre se distinguen por correo); los roles se siguen asignando en Seguridad. Solo aplica a enviados, se
  asigna al registrar y se reasigna al editar, con rastro en el historial. Solo se pueden asignar gestores con usuario;
  los que quedaron sin usuario de versiones anteriores se marcan como tales, no se pueden asignar y los oficios que ya
  los tenían los conservan.
- **Seguimiento** (menú *Seguimiento*, permiso `can_view_tracking`, rol `seguimiento` de solo consulta): tablero de los
  oficios enviados pendientes, en dos columnas (*Por entregar* = Generado y *Entregados sin evidencia*) con semáforo
  por antigüedad (verde, ámbar desde 7 días, rojo desde 15; ajustable con `OFICIOS_SEMAFORO_AMBAR` y
  `OFICIOS_SEMAFORO_ROJO`), quién trae cada uno y filtros por color y por gestor. Quien tiene este permiso ve todos
  los pendientes de las direcciones a las que tiene alcance, abre su detalle y sus archivos, pero no puede actuar
  ni ve el resto de documentos. Los concluidos, cancelados y recibidos no aparecen.
- Editar (`can_edit_oficio`): asunto, remitente o destinatario y fecha (en enviados, dentro del año del
  folio); en recibidos también el folio del remitente. Un cancelado no se edita. Cada cambio guarda el valor
  anterior, el nuevo, quién y el motivo opcional.
