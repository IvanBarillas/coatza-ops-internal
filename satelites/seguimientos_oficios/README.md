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

## OCR

Requiere `ocrmypdf` y `tesseract` con el idioma español en el proceso que ejecuta la cola
(`qcluster`), no en `web`. La imagen del worker del Core no los incluye: hace falta una imagen
propia para el worker. Sin ellos los adjuntos quedan con OCR en estado Error y se reintentan con:

```bash
python manage.py oficios_reprocesar_ocr
```

El PDF original nunca se modifica; solo se guarda el texto extraído. La búsqueda usa texto
completo en español con índice GIN en PostgreSQL y `icontains` en SQLite.

## Reglas de negocio

- El folio de los enviados sale de la **Nomenclatura** (dirección + clase), con contador por año.
  Se administra en el admin de Django hasta que exista su pantalla.
- Estados: Generado → Entregado → Concluido (con evidencia PDF); Cancelado desde cualquiera, con
  motivo. Cancelar un Concluido exige `can_cancel_concluded`. Los documentos no se eliminan.
- Director, dirección, folio, clase y sentido quedan congelados al registrar; el historial es
  solo de escritura.
