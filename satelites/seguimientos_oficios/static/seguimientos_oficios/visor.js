// Visor de PDF del módulo de oficios: abre en la página indicada y resalta las palabras buscadas.
import * as pdfjsLib from "./pdfjs/build/pdf.min.mjs";

globalThis.pdfjsLib = pdfjsLib;
const { EventBus, PDFViewer, PDFLinkService, PDFFindController } = await import("./pdfjs/web/pdf_viewer.mjs");

const base = new URL("./pdfjs/", import.meta.url).href;
pdfjsLib.GlobalWorkerOptions.workerSrc = base + "build/pdf.worker.min.mjs";

const cuerpo = document.body.dataset;
const estado = document.getElementById("estado");
const mostrarError = (mensaje) => {
    estado.textContent = mensaje;
    estado.hidden = false;
};

try {
    const eventBus = new EventBus();
    const linkService = new PDFLinkService({ eventBus });
    const findController = new PDFFindController({ eventBus, linkService });
    const visor = new PDFViewer({
        container: document.getElementById("contenedor"),
        viewer: document.getElementById("visor"),
        eventBus,
        linkService,
        findController,
    });
    linkService.setViewer(visor);

    const pagina = Math.max(1, parseInt(cuerpo.pagina, 10) || 1);
    const consulta = (cuerpo.consulta || "").trim();
    const contador = document.getElementById("coincidencias");
    // Varias palabras se resaltan por separado (un arreglo equivale a "cualquiera de ellas").
    const terminos = consulta.split(/\s+/).filter(Boolean);
    const buscar = (tipo, atras) => eventBus.dispatch("find", {
        source: window, type: tipo, query: terminos.length > 1 ? terminos : terminos[0], caseSensitive: false,
        entireWord: false, highlightAll: true, findPrevious: atras, matchDiacritics: false,
    });

    eventBus.on("updatefindmatchescount", ({ matchesCount }) => {
        contador.textContent = matchesCount.total
            ? `${matchesCount.current} de ${matchesCount.total} coincidencias`
            : "Sin coincidencias en este PDF";
    });
    let buscado = false;
    const iniciarBusqueda = () => {
        if (buscado || !consulta) return;
        buscado = true;
        buscar("", false);
    };
    eventBus.on("pagesinit", () => {
        visor.currentScaleValue = "page-width";
        visor.currentPageNumber = Math.min(pagina, visor.pagesCount);
        estado.hidden = true;
        if (consulta) {
            document.getElementById("navegacion").hidden = false;
            // El buscador necesita tener listo el texto del documento: se lanza al cargar las páginas
            // o, si tarda, a los pocos segundos.
            setTimeout(iniciarBusqueda, 2500);
        }
    });
    eventBus.on("pagesloaded", () => setTimeout(iniciarBusqueda, 200));
    document.getElementById("anterior").addEventListener("click", () => buscar("again", true));
    document.getElementById("siguiente").addEventListener("click", () => buscar("again", false));

    const documento = await pdfjsLib.getDocument({
        url: cuerpo.pdf,
        withCredentials: true,
        wasmUrl: base + "wasm/",
        iccUrl: base + "iccs/",
        standardFontDataUrl: base + "standard_fonts/",
    }).promise;
    visor.setDocument(documento);
    linkService.setDocument(documento);
    document.getElementById("paginas").textContent = `${documento.numPages} pág.`;
} catch (error) {
    console.error(error);
    mostrarError("No se pudo abrir el PDF en el visor. Usa “Descargar PDF”.");
}
