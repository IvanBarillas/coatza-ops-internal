import datetime

from django.test import override_settings
from django.urls import reverse

from satelites.telefonia import services
from satelites.telefonia.models import Linea, Reporte

from .base import HOY, PNG, BaseTelefonia, png

SIN_MANIFIESTO = override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})


def url(nombre, *args):
    return reverse(f"telefonia:{nombre}", args=args)


@SIN_MANIFIESTO
class VistasTelefoniaTests(BaseTelefonia):
    def reporte(self, **extra):
        datos = dict(usuario=self.operador, linea=self.linea, folio="11986221", levantado=HOY, detalle="Sin tono",
                     contacto_nombre="Ana", contacto_telefono="9212223344", responsable=self.tecnico)
        return services.crear_reporte(**{**datos, **extra})

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def negado(self, respuesta):
        self.assertIn(respuesta.status_code, (302, 403))

    # ---- entrada y menú
    def test_inicio_lleva_a_cada_quien_a_su_vista(self):
        self.entrar(self.operador)
        self.assertRedirects(self.client.get(url("inicio")), url("reportes"), fetch_redirect_response=False)
        self.entrar(self.tecnico)
        self.assertRedirects(self.client.get(url("inicio")), url("mis_pendientes"), fetch_redirect_response=False)

    def test_el_menu_depende_del_rol(self):
        self.entrar(self.operador)
        nombres = [i["name"] for i in self.client.get(url("reportes")).context["sidebar_items"]]
        self.assertEqual(nombres, ["Reportes", "Mis pendientes", "Nuevo reporte", "Mapa", "Líneas"])
        self.entrar(self.tecnico)
        self.assertEqual([i["name"] for i in self.client.get(url("mis_pendientes")).context["sidebar_items"]], ["Mis pendientes"])
        self.entrar(self.lector)
        self.assertEqual([i["name"] for i in self.client.get(url("reportes")).context["sidebar_items"]], ["Reportes", "Mapa", "Líneas"])

    # ---- permisos
    def test_permisos_por_rol(self):
        r = self.reporte()
        self.entrar(self.lector)
        self.negado(self.client.get(url("reporte_crear")))
        self.negado(self.client.post(url("reporte_comentar", r.pk), {"texto": "hola"}))
        self.negado(self.client.get(url("linea_crear")))
        self.entrar(self.tecnico)
        self.negado(self.client.get(url("reportes")))
        self.negado(self.client.get(url("mapa")))
        self.negado(self.client.get(url("reporte_editar", r.pk)))
        self.negado(self.client.post(url("reporte_cancelar", r.pk), {"motivo": "Duplicado del otro"}))
        self.entrar(self.operador)
        self.negado(self.client.post(url("reporte_cancelar", r.pk), {"motivo": "Duplicado del otro"}))  # operador no cancela
        self.entrar(self.dueno)
        self.client.post(url("reporte_cancelar", r.pk), {"motivo": "Duplicado del otro"})
        r.refresh_from_db()
        self.assertEqual(r.estatus, "cancelado")

    def test_el_tecnico_solo_toca_sus_reportes(self):
        propio, ajeno = self.reporte(folio="P-1"), self.reporte(folio="A-1", responsable=self.otro_tecnico)
        self.entrar(self.tecnico)
        self.assertEqual(self.client.get(url("reporte_detalle", propio.pk)).status_code, 200)
        self.assertEqual(self.client.get(url("reporte_detalle", ajeno.pk)).status_code, 404)
        self.client.post(url("reporte_comentar", ajeno.pk), {"texto": "intento"})
        self.assertFalse(ajeno.movimientos.filter(tipo="comentario").exists())
        self.assertEqual([r.folio for r in self.client.get(url("mis_pendientes")).context["pendientes"]], ["P-1"])

    # ---- reportes
    def test_lista_con_pestañas_busqueda_y_semaforo(self):
        self.reporte(folio="VIEJO", levantado=HOY - datetime.timedelta(days=10))
        self.reporte(folio="NUEVO", levantado=HOY)
        atendido = self.reporte(folio="LISTO")
        services.marcar_atendido(atendido, usuario=self.tecnico)
        self.entrar(self.operador)
        pagina = self.client.get(url("reportes"))
        self.assertEqual([r.folio for r in pagina.context["pagina"]], ["VIEJO", "NUEVO"])  # más antiguo primero
        self.assertEqual({t["clave"]: t["total"] for t in pagina.context["tabs"]}, {"pendientes": 2, "atendidos": 1, "cancelados": 0, "todos": 3})
        self.assertEqual([r.folio for r in self.client.get(url("reportes"), {"semaforo": "rojo"}).context["pagina"]], ["VIEJO"])
        self.assertEqual([r.folio for r in self.client.get(url("reportes"), {"tab": "atendidos"}).context["pagina"]], ["LISTO"])
        self.assertEqual([r.folio for r in self.client.get(url("reportes"), {"tab": "todos", "q": "allende nuevo"}).context["pagina"]], ["NUEVO"])

    def test_crear_reporte_por_formulario(self):
        self.entrar(self.operador)
        pagina = self.client.get(url("reporte_crear"), {"linea": str(self.linea.pk)})
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Buscar línea")
        self.assertEqual(pagina.context["linea_inicial"], str(self.linea.pk))
        r = self.client.post(url("reporte_crear"), {
            "linea": self.linea.pk, "folio": "12007219", "levantado": HOY.isoformat(), "detalle": "Sin internet",
            "responsable": self.tecnico.pk, "contacto_nombre": "", "contacto_telefono": "",
        })
        reporte = Reporte.objects.get()
        self.assertRedirects(r, url("reporte_detalle", reporte.pk))
        self.assertEqual((reporte.contacto_nombre, reporte.responsable), ("Tomás Técnico", self.tecnico))
        repetido = self.client.post(url("reporte_crear"), {"linea": self.linea.pk, "folio": "12007219", "levantado": HOY.isoformat(), "contacto_nombre": "X", "contacto_telefono": "1"})
        self.assertEqual(repetido.status_code, 200)
        self.assertContains(repetido, "Ya existe un reporte con el folio")
        self.assertEqual(Reporte.objects.count(), 1)

    def test_flujo_completo_en_el_detalle(self):
        r = self.reporte()
        self.entrar(self.tecnico)
        detalle = self.client.get(url("reporte_detalle", r.pk))
        self.assertContains(detalle, "Agregar comentario")
        self.client.post(url("reporte_comentar", r.pk), {"texto": "Visita 1: nadie en sitio"})
        self.client.post(url("reporte_evidencia", r.pk), {"archivo": png(), "tipo": "foto"})
        self.client.post(url("reporte_atender", r.pk), {"comentario": "Telmex ya validó"})
        r.refresh_from_db()
        self.assertEqual(r.estatus, "atendido")
        self.assertEqual([m.tipo for m in r.movimientos.all()], ["creado", "comentario", "evidencia", "atendido"])
        evidencia = r.evidencias.get()
        descarga = self.client.get(url("evidencia_descargar", r.pk, evidencia.pk))
        self.assertEqual((descarga.status_code, descarga["Content-Type"], b"".join(descarga.streaming_content)), (200, "image/png", PNG))
        self.entrar(self.otro_tecnico)
        self.assertEqual(self.client.get(url("evidencia_descargar", r.pk, evidencia.pk)).status_code, 404)

    def test_evidencia_invalida_muestra_error_y_no_guarda(self):
        r = self.reporte()
        self.entrar(self.tecnico)
        from django.core.files.uploadedfile import SimpleUploadedFile

        respuesta = self.client.post(url("reporte_evidencia", r.pk), {"archivo": SimpleUploadedFile("a.txt", b"texto"), "tipo": "foto"}, follow=True)
        self.assertContains(respuesta, "Formato no admitido")
        self.assertFalse(r.evidencias.exists())

    def test_corregir_y_reasignar_como_operador(self):
        r = self.reporte()
        self.entrar(self.operador)
        self.assertEqual(self.client.get(url("reporte_editar", r.pk)).status_code, 200)
        self.client.post(url("reporte_editar", r.pk), {
            "folio": "11986221", "levantado": HOY.isoformat(), "detalle": "Sin tono y ruido", "contacto_nombre": "Ana", "contacto_telefono": "9212223344", "motivo": "",
        })
        r.refresh_from_db()
        self.assertEqual(r.detalle, "Sin tono y ruido")
        self.client.post(url("reporte_asignar", r.pk), {"responsable": self.otro_tecnico.pk})
        r.refresh_from_db()
        self.assertEqual(r.responsable, self.otro_tecnico)

    def test_carga_parcial_htmx(self):
        self.entrar(self.operador)
        parcial = self.client.get(url("reportes"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="page-content")
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, "Reportes")

    # ---- líneas y mapa
    def test_alta_de_linea_con_enlace_de_google_maps(self):
        self.entrar(self.operador)
        r = self.client.post(url("linea_crear"), {
            "identificador": " 9212 110336 ", "sitio": "Duport", "tipo": "internet", "municipio": "Coatzacoalcos", "velocidad": "300 Mb",
            "direccion": "Unidad Deportiva", "latitud": "", "longitud": "", "notas": "", "is_active": "on",
            "enlace_maps": "https://www.google.com/maps/place/D/@18.1512,-94.4256,17z",
        })
        linea = Linea.objects.get(sitio="Duport")
        self.assertRedirects(r, url("linea_detalle", linea.pk))
        self.assertEqual((linea.identificador, float(linea.latitud), float(linea.longitud)), ("9212 110336", 18.1512, -94.4256))
        repetida = self.client.post(url("linea_crear"), {"identificador": "9212110336", "sitio": "Otra", "tipo": "telefono", "municipio": "C"})
        self.assertContains(repetida, "Ya existe una línea con ese número")
        corto = self.client.post(url("linea_crear"), {"identificador": "111", "sitio": "X", "tipo": "telefono", "municipio": "C", "enlace_maps": "https://maps.app.goo.gl/abc"})
        self.assertContains(corto, "No se encontraron coordenadas")

    def test_lista_de_lineas_y_mapa(self):
        Linea.objects.create(identificador="C1G-2204-0353", sitio="Site Tesorería", tipo="enlace")
        self.reporte(levantado=HOY - datetime.timedelta(days=8))
        self.entrar(self.lector)
        lista = self.client.get(url("lineas"))
        self.assertEqual({l.identificador: l.estado for l in lista.context["pagina"]}, {"9212165053": "rojo", "C1G-2204-0353": "ninguno"})
        self.assertEqual([l.identificador for l in self.client.get(url("lineas"), {"tipo": "enlace"}).context["pagina"]], ["C1G-2204-0353"])
        mapa = self.client.get(url("mapa"))
        self.assertEqual((mapa.context["con_mapa"], mapa.context["sin_mapa"]), (1, 1))
        self.assertContains(mapa, "leaflet.js")
        detalle = self.client.get(url("linea_detalle", self.linea.pk))
        self.assertContains(detalle, "https://www.google.com/maps?q=18.15")
