# PDF.js (visor de PDF del módulo de oficios)

- Paquete: `pdfjs-dist` 6.3.289 (npm), publicado por Mozilla — https://github.com/mozilla/pdf.js
- Licencia: Apache-2.0 (`LICENSE`); los decodificadores WebAssembly traen sus licencias en `wasm/LICENSE_*`.
- Tarball: https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.3.289.tgz
- SHA-256 del tarball: `06f25e887adc6489f04c9fcb14198c77e4e5623a59a0bba5c4cea5838a4f1241`
- Archivos incluidos (sin modificar): `build/pdf.min.mjs`, `build/pdf.worker.min.mjs`, `web/pdf_viewer.mjs`,
  `web/pdf_viewer.css`, `web/images/`, `wasm/{jbig2,openjpeg,qcms_bg}.wasm`, `iccs/`, `standard_fonts/`.
- No se incluyen los mapas de fuentes (`cmaps`), el sandbox de scripting ni los `.map`.
- Para actualizar: descargar la nueva versión, verificar el hash publicado por npm, reemplazar estos archivos y
  probar el visor (resaltado y salto de página) con un PDF escaneado y uno digital.
