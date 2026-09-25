# Telefonía y enlaces

App satélite propia (no toca el Core). Lleva el catálogo de líneas y enlaces del municipio, con su ubicación en el mapa, y el
seguimiento de los **reportes de falla a Telmex**. Reglas de agnosticismo: `AGENTS.md` (sección «Apps satélite propias»): el único
punto de contacto con el Core es `integracion.py`.

## Activación

```env
AXENTRA_EXTRA_APPS=satelites.seguimientos_oficios,satelites.telefonia
```

Después: `migrate`, `check_axentra_modules --persist`, activar el módulo en el Hub y dar membresía a los usuarios. Funciona sola
(sin el satélite de oficios).

| Variable | Uso | Por defecto |
|---|---|---|
| `TEL_ARCHIVOS_ROOT` | Almacén de fotos y capturas de los reportes | `MEDIA_ROOT/telefonia` |
| `TEL_SEMAFORO_AMBAR` / `TEL_SEMAFORO_ROJO` | Días abierto desde los que un reporte pasa a ámbar y a rojo | `3` / `7` |
| `TEL_MAPA_TILES_URL` / `TEL_MAPA_ATRIBUCION` | Proveedor de mosaicos del mapa (plantilla Leaflet, p. ej. `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`) y su atribución. Sirve para cambiar de proveedor si el actual bloquea la IP de la institución | OpenStreetMap |

## Cómo se trabaja

1. Se cae una línea o un enlace: se llama al 01800 de Telmex, que da un **folio**.
2. **Nuevo reporte:** se busca la línea por número, circuito, sitio o dirección (o tocándola en el mapa), se captura el folio, la
   fecha, el detalle y el **contacto en sitio** (nombre y teléfono: a quien Telmex le marcará para validar). El contacto puede ser
   alguien externo; opcionalmente se asigna un **responsable de Innovación** (usuario del sistema) que da seguimiento y ve el
   reporte en *Mis pendientes*. Si se elige responsable y se dejan vacíos los datos del contacto, se toman de su cuenta.
3. Cuando el técnico de Telmex termina, Innovación avisa: el reporte se marca **Atendido** (con fecha; sin fecha, hoy).
4. La **evidencia** (foto, captura de una prueba de velocidad, PDF) es **opcional**, antes o después de atender.
5. Los **comentarios** dan el contexto de visita en visita («fui pero no se terminó, regreso mañana»): quedan en el seguimiento del
   reporte junto con todo lo demás (alta, evidencia, atendido, cancelado, correcciones), que es de solo escritura.

Estatus: **Pendiente**, **Atendido** y **Cancelado** (con motivo: duplicado, Telmex lo cerró…); un atendido o cancelado se puede
**reabrir** con motivo. La lista abre en Pendientes, del más antiguo al más nuevo, con **semáforo por días abiertos**
(verde < 3, ámbar 3 a 6, rojo 7 o más; ajustable) y filtro por color. El folio de Telmex no se repite. Se puede corregir folio,
fecha, detalle y contacto (con historial); la línea no cambia: se cancela y se levanta otro. Una línea conserva su historial de
reportes (reincidencias) y avisa si ya tiene uno abierto.

## Líneas y mapa

Catálogo (*Líneas*): número o circuito (único; ignora espacios y mayúsculas), sitio, tipo (línea telefónica, internet, enlace
dedicado, otro), paquete o velocidad, municipio, dirección y coordenadas. Para ubicarlas basta pegar el **enlace largo de Google
Maps** (o «latitud, longitud»): se llenan solas; los enlaces cortos (`maps.app.goo.gl`) no se pueden leer sin internet desde el
servidor. El mapa (*Mapa*) usa Leaflet con OpenStreetMap (incluido en `static/telefonia/leaflet/`, ver `PROCEDENCIA.md`, sin CDN;
solo los mosaicos se piden a openstreetmap.org, enviando el dominio como `Referer` como exige su política de uso; si «Access blocked» aparece en el mapa es que OSM está limitando la IP, y se cambia de proveedor con las variables `TEL_MAPA_*`) y colorea cada línea por su reporte abierto más antiguo. Cada línea tiene
«Abrir en Google Maps».

**Importar lo que ya tienen los compañeros de campo:**

```bash
python manage.py telefonia_importar_lineas archivo.kml            # simula
python manage.py telefonia_importar_lineas archivo.kml --aplicar  # escribe
```

Acepta el KML exportado de Google «Mis mapas» (título, coordenadas y las líneas «Municipio:, Nombre:, Dirección:, Teléfono:,
Paquete:, Velocidad:» de la descripción) o un CSV con columnas flexibles (`telefono`/`linea`, `sitio`/`nombre`, `latitud`,
`longitud`, `enlace_maps`…). Es repetible: actualiza por número o circuito, sin duplicar ni borrar datos que el archivo no trae.
El tipo se deduce: con letras es enlace, con «internet» en el paquete es internet, si no, línea telefónica.

## Roles (uno por usuario y módulo)

| Rol | Puede |
|---|---|
| `owner` | Todo, incluido cancelar/reabrir reportes |
| `operador` | Ver, registrar, comentar, subir evidencia, atender, reasignar y corregir reportes; administrar líneas |
| `tecnico` | Solo *Mis pendientes*: comentar, subir evidencia y marcar atendidos los reportes que tiene asignados |
| `viewer` | Consultar reportes, líneas y mapa |

Los datos son de toda la institución para quien tenga membresía (no se filtran por dependencia): lo maneja Innovación.
Las evidencias solo se descargan por una vista autenticada; aceptan JPG, PNG, WebP y PDF de hasta 15 MB (HEIC no).
