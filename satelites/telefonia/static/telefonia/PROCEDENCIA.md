# Procedencia de las bibliotecas incluidas

## Leaflet 1.9.4 (`leaflet/`)
- Origen: https://unpkg.com/leaflet@1.9.4/dist/ (paquete npm `leaflet@1.9.4`), descargado el 2026-09-25.
- Licencia: BSD 2-Clause (`leaflet/LICENSE`).
- Modificación: a `leaflet.js` se le quitó la última línea (`//# sourceMappingURL=leaflet.js.map`), porque el mapa de depuración no se incluye y el paso de estáticos de producción (WhiteNoise, manifiesto) falla si el archivo referenciado no existe.
- SHA-256: `leaflet.js` original = `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a`; el incluido, ya sin esa línea, = `c973489bbc5ac530af0ffd1016a88122d3fa02b7b0c8de375ed906e04a46d10f`;
  `leaflet.css` = `a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6`.
- Para actualizar: descargar de la misma ruta con la nueva versión, reemplazar `leaflet/`, actualizar esta nota y probar el mapa.

## Mapa base
Los mosaicos se piden a OpenStreetMap (`tile.openstreetmap.org`) desde el navegador; uso ligero permitido por su política
(https://operations.osmfoundation.org/policies/tiles/). Si algún día el tráfico crece, cambiar la URL en `mapa.js` por un
servidor de mosaicos propio o de pago.
