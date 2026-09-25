/* Mapa de líneas (Leaflet + OpenStreetMap). Cada elemento [data-tel-mapa] con data-lineas="<id de un json_script>" se
   convierte en un mapa. Los marcadores se colorean por estado (rojo/ámbar/verde según el reporte más viejo abierto, gris sin
   reportes) y al hacer clic disparan el evento `tel-linea` con {id}, que el formulario de reportes usa para elegir la línea. */
(function () {
    var TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    var ATRIBUCION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    var COLORES = { rojo: '#dc2626', ambar: '#d97706', verde: '#059669', ninguno: '#6b7280' };
    var COATZACOALCOS = [18.15, -94.42];

    function leerLineas(el) {
        var origen = document.getElementById(el.getAttribute('data-lineas'));
        try { return origen ? JSON.parse(origen.textContent) : []; } catch (e) { return []; }
    }

    function popup(linea) {
        var caja = document.createElement('div');
        var titulo = document.createElement('strong');
        titulo.textContent = linea.sitio;
        caja.appendChild(titulo);
        caja.appendChild(document.createElement('br'));
        caja.appendChild(document.createTextNode(linea.identificador + (linea.abiertos ? ' · ' + linea.abiertos + ' reporte(s) abierto(s)' : '')));
        return caja;
    }

    function iniciar(el) {
        if (el.getAttribute('data-listo') || !window.L) { return; }
        el.setAttribute('data-listo', '1');
        var lineas = leerLineas(el).filter(function (l) { return l.lat !== null && l.lng !== null; });
        var mapa = L.map(el, { scrollWheelZoom: false }).setView(COATZACOALCOS, 12);
        L.tileLayer(TILES, { maxZoom: 19, attribution: ATRIBUCION }).addTo(mapa);
        var marcadores = {};
        lineas.forEach(function (linea) {
            var marcador = L.circleMarker([linea.lat, linea.lng], {
                radius: 9, color: '#111827', weight: 1, fillColor: COLORES[linea.estado] || COLORES.ninguno, fillOpacity: 0.9,
            }).addTo(mapa);
            marcador.bindPopup(popup(linea));
            marcador.on('click', function () {
                el.dispatchEvent(new CustomEvent('tel-linea', { detail: { id: linea.id }, bubbles: true }));
            });
            marcadores[linea.id] = marcador;
        });
        if (lineas.length === 1) {
            mapa.setView([lineas[0].lat, lineas[0].lng], 16);
        } else if (lineas.length > 1) {
            mapa.fitBounds(L.featureGroup(Object.values(marcadores)).getBounds().pad(0.15));
        }
        el._tel = {
            mapa: mapa,
            enfocar: function (id) {
                var marcador = marcadores[id];
                if (!marcador) { return; }
                mapa.setView(marcador.getLatLng(), Math.max(mapa.getZoom(), 16));
                marcador.openPopup();
            },
        };
        setTimeout(function () { mapa.invalidateSize(); }, 200);
    }

    function escanear() {
        document.querySelectorAll('[data-tel-mapa]').forEach(iniciar);
    }

    // Leaflet y este archivo pueden cargarse en cualquier orden cuando la página llega por HTMX: se espera a que exista L.
    var intentos = 0;
    var espera = setInterval(function () {
        if (window.L) { clearInterval(espera); escanear(); } else if (++intentos > 100) { clearInterval(espera); }
    }, 50);
    window.TelMapa = {
        escanear: escanear,
        enfocar: function (el, id) { if (el && el._tel) { el._tel.enfocar(id); } },
    };
})();
