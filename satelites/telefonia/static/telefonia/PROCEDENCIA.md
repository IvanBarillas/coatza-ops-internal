# Procedencia de las bibliotecas incluidas

## Leaflet 1.9.4 (`leaflet/`)
- Origen: https://unpkg.com/leaflet@1.9.4/dist/ (paquete npm `leaflet@1.9.4`), descargado el 2026-09-25.
- Licencia: BSD 2-Clause (`leaflet/LICENSE`).
- SHA-256: `leaflet.js` = `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a`,
  `leaflet.css` = `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6`.
- Para actualizar: descargar de la misma ruta con la nueva versión, reemplazar `leaflet/`, actualizar esta nota y probar el mapa.

## Mapa base
Los mosaicos se piden a OpenStreetMap (`tile.openstreetmap.org`) desde el navegador; uso ligero permitido por su política
(https://operations.osmfoundation.org/policies/tiles/). Si algún día el tráfico crece, cambiar la URL en `mapa.js` por un
servidor de mosaicos propio o de pago.
