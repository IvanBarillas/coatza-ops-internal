/* Mapa de líneas (Leaflet + OpenStreetMap). Cada elemento [data-tel-mapa] con data-lineas="<id de un json_script>" se
   convierte en un mapa. Los marcadores se colorean por estado (rojo/ámbar/verde según el reporte más viejo abierto, gris sin
   reportes) y al hacer clic disparan el evento `tel-linea` con {id}, que el formulario de reportes usa para elegir la línea. */
(function () {
    // Por defecto OpenStreetMap (gratis). Si el proveedor limita la IP de la institución, se cambia por entorno con
    // TEL_MAPA_TILES_URL / TEL_MAPA_ATRIBUCION (llegan en data-tiles / data-atribucion). Ojo: los proveedores alternativos
    // gratuitos piden una llave (los mosaicos de CARTO sin llave salen con la marca «API KEY REQUIRED»).
    var TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    var ATRIBUCION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
    // La app manda Referrer-Policy: same-origin y los proveedores de mosaicos piden un Referer válido: por eso los mosaicos
    // piden explícitamente que se envíe el origen (solo el dominio, sin ruta).
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
        capa(el).addTo(mapa);
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

    function capa(el) {
        return L.tileLayer(el.getAttribute('data-tiles') || TILES, {
            maxZoom: 19, subdomains: 'abcd', attribution: el.getAttribute('data-atribucion') || ATRIBUCION, referrerPolicy: 'origin',
        });
    }

    /* Selector de ubicación (formulario de líneas): un clic en el mapa coloca el marcador y llena latitud y longitud; el marcador
       se puede arrastrar; y si se escriben las coordenadas a mano, el marcador las sigue. */
    function iniciarSelector(el) {
        if (el.getAttribute('data-listo') || !window.L) { return; }
        el.setAttribute('data-listo', '1');
        var latitud = document.getElementById(el.getAttribute('data-lat-input'));
        var longitud = document.getElementById(el.getAttribute('data-lng-input'));
        if (!latitud || !longitud) { return; }
        var mapa = L.map(el, { scrollWheelZoom: true }).setView(COATZACOALCOS, 12);
        capa(el).addTo(mapa);
        var marcador = null;

        function fijar(lat, lng, centrar) {
            var punto = [lat, lng];
            if (marcador) { marcador.setLatLng(punto); } else {
                marcador = L.marker(punto, { draggable: true }).addTo(mapa);
                marcador.on('dragend', function () { escribir(marcador.getLatLng()); });
            }
            if (centrar) { mapa.setView(punto, Math.max(mapa.getZoom(), 16)); }
        }
        function escribir(punto) {
            latitud.value = punto.lat.toFixed(6);
            longitud.value = punto.lng.toFixed(6);
            latitud.dispatchEvent(new Event('input', { bubbles: true }));
            longitud.dispatchEvent(new Event('input', { bubbles: true }));
        }
        function desdeCampos() {
            var lat = parseFloat(latitud.value), lng = parseFloat(longitud.value);
            if (isFinite(lat) && isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) { fijar(lat, lng, true); }
        }
        mapa.on('click', function (evento) { fijar(evento.latlng.lat, evento.latlng.lng, false); escribir(evento.latlng); });
        latitud.addEventListener('change', desdeCampos);
        longitud.addEventListener('change', desdeCampos);
        desdeCampos();
        el._tel = { mapa: mapa };
        setTimeout(function () { mapa.invalidateSize(); }, 200);
    }

    function escanear() {
        document.querySelectorAll('[data-tel-mapa]').forEach(iniciar);
        document.querySelectorAll('[data-tel-selector]').forEach(iniciarSelector);
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
