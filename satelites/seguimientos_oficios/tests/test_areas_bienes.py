import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Bien, HistorialBien, Prestamo
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.prestamos.services import (
    exigir_motivo_de_estado, foto_bien, registrar_alta_bien, registrar_cambios_bien, registrar_devolucion,
)
from satelites.seguimientos_oficios.services import cancelar_documento

from .test_prestamos import HOY, PrestamosBase


class AreasDelMenuTests(PrestamosBase):
    def menu(self, nombre):
        return self.client.get(reverse(f"seguimientos_oficios:{nombre}"))

    def test_el_menu_cambia_de_opciones_segun_el_area(self):
        oficios = self.menu("documento_list")
        self.assertEqual(oficios.context["area_actual"]["clave"], "oficios")
        nombres = [i["name"] for i in oficios.context["sidebar_items"]]
        self.assertIn("Documentos", nombres)
        self.assertNotIn("Bienes", nombres)
        prestamos = self.menu("bienes")
        self.assertEqual(prestamos.context["area_actual"]["clave"], "prestamos")
        nombres = [i["name"] for i in prestamos.context["sidebar_items"]]
        self.assertEqual(nombres, ["Seguimiento de préstamos", "Vales", "Bienes", "Nuevo vale"])
        self.assertEqual([a["clave"] for a in prestamos.context["sidebar_areas"]], ["oficios", "prestamos"])

    def test_el_vale_abierto_desde_su_detalle_mantiene_el_area_de_prestamos(self):
        documento, _ = self.vale()
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertEqual(detalle.context["area_actual"]["clave"], "prestamos")

    def test_quien_solo_tiene_un_area_no_ve_selector(self):
        UserAppRole.objects.filter(user=self.user).update(role="editor", permissions_list=P.ROLE_MAPPING["editor"])
        pagina = self.menu("documento_list")
        self.assertEqual(pagina.context["sidebar_areas"], [])
        self.assertEqual(pagina.context["area_actual"]["clave"], "oficios")

    def test_marca_la_opcion_activa(self):
        pagina = self.menu("vales")
        self.assertEqual([i["name"] for i in pagina.context["sidebar_items"] if i["active"]], ["Vales"])


class CatalogosEnOficiosTests(PrestamosBase):
    def setUp(self):
        super().setUp()
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])

    def menu(self, nombre):
        return self.client.get(reverse(f"seguimientos_oficios:{nombre}"))

    def test_catalogos_solo_aparece_en_oficios(self):
        oficios = [i["name"] for i in self.menu("documento_list").context["sidebar_items"]]
        self.assertIn("Catálogos", oficios)
        pagina = self.menu("catalogos")
        self.assertEqual(pagina.context["area_actual"]["clave"], "oficios")
        self.assertNotIn("Catálogos", [i["name"] for i in self.menu("bienes").context["sidebar_items"]])

    def test_direccion_abre_la_seccion_pedida_y_solo_esa_por_defecto(self):
        url = reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk])
        self.assertEqual(self.client.get(url).context["seccion"], "nomenclaturas")
        self.assertEqual(self.client.get(url + "?seccion=gestores").context["seccion"], "gestores")
        self.assertEqual(self.client.get(url + "?seccion=otra").context["seccion"], "nomenclaturas")

    def test_agregar_categoria_vuelve_a_la_seccion_de_categorias(self):
        url = reverse("seguimientos_oficios:categoria_crear", args=[self.direccion.pk])
        respuesta = self.client.post(url, {"nombre": "Panteones"})
        self.assertTrue(respuesta["Location"].endswith("?seccion=categorias"))


class TableroDePrestamosTests(PrestamosBase):
    def prestamo(self, dias_limite, bien=None):
        return self.vale([bien or self.bien(f"Bien {dias_limite}")], limite=HOY + datetime.timedelta(days=dias_limite))

    def tablero(self, hoy=HOY + datetime.timedelta(days=5), **parametros):
        with mock.patch("django.utils.timezone.localdate", return_value=hoy):
            return self.client.get(reverse("seguimientos_oficios:prestamos"), parametros)

    def test_semaforo_por_fecha_limite_y_orden_por_urgencia(self):
        self.prestamo(1)    # vencido (hoy = HOY+5, límite HOY+1)
        self.prestamo(6)    # por vencer (límite HOY+6, hoy HOY+5)
        self.prestamo(20)   # vigente
        respuesta = self.tablero()
        self.assertEqual({t["clave"]: t["total"] for t in respuesta.context["tiles"]}, {"rojo": 1, "ambar": 1, "verde": 1})
        self.assertEqual([p.color for p in respuesta.context["prestamos"]], ["rojo", "ambar", "verde"])
        self.assertContains(respuesta, "Vencido hace 4 días")
        self.assertContains(respuesta, "Faltan 1 día")

    def test_filtra_por_color_y_ignora_valores_invalidos(self):
        self.prestamo(1)
        self.prestamo(20)
        self.assertEqual(len(self.tablero(color="rojo").context["prestamos"]), 1)
        self.assertEqual(len(self.tablero(color="verde").context["prestamos"]), 1)
        self.assertEqual(len(self.tablero(color="inventado").context["prestamos"]), 2)

    def test_devueltos_y_cancelados_no_aparecen(self):
        documento, prestamo = self.prestamo(1)
        registrar_devolucion(prestamo, usuario=self.user, fecha=HOY)
        otro, _ = self.prestamo(2)
        cancelar_documento(otro, usuario=self.user, motivo="Se prestó el bien equivocado")
        self.assertEqual(self.tablero().context["prestamos"], [])
        self.assertContains(self.tablero(), "No hay bienes prestados en este momento")

    def test_el_aviso_es_configurable_por_entorno(self):
        self.prestamo(6)
        with mock.patch("satelites.seguimientos_oficios.integracion.valor_entorno", return_value="0"):
            self.assertEqual(self.tablero().context["prestamos"][0].color, "verde")
        self.assertEqual(self.tablero().context["prestamos"][0].color, "ambar")

    def test_bienes_muestra_contadores_por_situacion(self):
        self.vale([self.starlink])
        Bien.objects.filter(pk=self.laptop.pk).update(estado="baja")
        tabs = {t["clave"]: t["total"] for t in self.client.get(reverse("seguimientos_oficios:bienes")).context["tabs"]}
        self.assertEqual(tabs, {"todos": 2, "disponible": 0, "prestado": 1, "en_reparacion": 0, "baja": 1})


class DetalleYBitacoraDelBienTests(PrestamosBase):
    def entradas(self, bien):
        return list(bien.historial.values_list("accion", flat=True))

    def test_reglas_del_motivo(self):
        for nuevo in ("en_reparacion", "baja"):
            with self.assertRaises(ValidationError):
                exigir_motivo_de_estado("disponible", nuevo, "  ")
            with self.assertRaises(ValidationError):
                exigir_motivo_de_estado("disponible", nuevo, "abc")
            exigir_motivo_de_estado("disponible", nuevo, "No enciende")
        exigir_motivo_de_estado("baja", "disponible", "")          # volver a disponible: opcional
        exigir_motivo_de_estado("en_reparacion", "en_reparacion", "")  # sin cambio de estado

    def test_alta_cambios_y_estado_quedan_en_la_bitacora(self):
        bien = self.bien("Switch", "SW-1")
        registrar_alta_bien(bien, usuario=self.user)
        antes = foto_bien(bien)
        bien.nombre, bien.identificador = "Switch 24p", "SW-1B"
        bien.save()
        registrar_cambios_bien(bien, antes, usuario=self.user)
        antes = foto_bien(bien)
        bien.estado = "en_reparacion"
        bien.save()
        registrar_cambios_bien(bien, antes, usuario=self.user, motivo="Puerto dañado")
        self.assertEqual(self.entradas(bien), ["alta", "editado", "estado"])
        estado = bien.historial.get(accion="estado")
        self.assertEqual(estado.datos["cambios"]["estado"], {"antes": "disponible", "despues": "en_reparacion"})
        self.assertEqual((estado.datos["motivo"], estado.usuario_nombre), ("Puerto dañado", self.user.full_name or self.user.email))
        self.assertIsNone(registrar_cambios_bien(bien, foto_bien(bien), usuario=self.user))

    def test_la_bitacora_solo_se_escribe(self):
        registrar_alta_bien(self.starlink, usuario=self.user)
        entrada = self.starlink.historial.get()
        entrada.datos = {}
        with self.assertRaises(ValueError):
            entrada.save()
        with self.assertRaises(ValueError):
            entrada.delete()

    def test_prestamo_devolucion_y_cancelacion_dejan_su_movimiento(self):
        documento, prestamo = self.vale([self.starlink])
        registrar_devolucion(prestamo, usuario=self.user, fecha=HOY, observaciones="Completo")
        otro, _ = self.vale([self.starlink])
        cancelar_documento(otro, usuario=self.user, motivo="Se prestó el bien equivocado")
        self.assertEqual(self.entradas(self.starlink), ["prestamo", "devolucion", "prestamo", "liberado"])
        prestamo_entrada = self.starlink.historial.filter(accion="prestamo").first()
        self.assertEqual(prestamo_entrada.datos["folio"], documento.folio)
        self.assertEqual(self.starlink.historial.get(accion="devolucion").datos["observaciones"], "Completo")

    def test_pantalla_de_edicion_exige_motivo_y_lo_guarda(self):
        editar = reverse("seguimientos_oficios:bien_editar", args=[self.laptop.pk])
        datos = {"nombre": "Laptop", "identificador": "LT-77", "folio_inventario": "", "descripcion": "", "estado": "en_reparacion", "motivo": ""}
        self.assertEqual(self.client.post(editar, datos).status_code, 200)
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "disponible")
        self.assertEqual(self.client.post(editar, {**datos, "motivo": "Pantalla rota"}).status_code, 302)
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "en_reparacion")
        self.assertEqual(self.laptop.historial.get(accion="estado").datos["motivo"], "Pantalla rota")
        volver = self.client.post(editar, {**datos, "estado": "disponible", "motivo": ""})
        self.assertEqual(volver.status_code, 302)  # al volver a disponible el motivo es opcional

    def test_detalle_muestra_datos_historial_de_prestamos_y_bitacora(self):
        registrar_alta_bien(self.starlink, usuario=self.user)
        documento, prestamo = self.vale([self.starlink])
        with mock.patch("django.utils.timezone.localdate", return_value=HOY):
            registrar_devolucion(prestamo, usuario=self.user, fecha=HOY)
        self.vale([self.starlink], limite=HOY + datetime.timedelta(days=30))
        pagina = self.client.get(reverse("seguimientos_oficios:bien_detalle", args=[self.starlink.pk]))
        for texto in ("Starlink", "SL-001", "INV-100", "Historial de préstamos", "Bitácora de movimientos", documento.folio, "Alta", "Prestado", "Devuelto", "EGRESOS", "Lo tiene"):
            self.assertContains(pagina, texto)
        self.assertEqual(len(pagina.context["asignaciones"]), 2)
        self.assertEqual(pagina.context["situacion"], "prestado")
        self.assertContains(pagina, reverse("seguimientos_oficios:bien_editar", args=[self.starlink.pk]))

    def test_el_detalle_respeta_el_alcance_y_el_permiso(self):
        from satelites.seguimientos_oficios.models import Direccion

        otra = Direccion.objects.create(nombre="Egresos", folio_manual=False, vales_habilitados=True)
        ajeno = Bien.objects.create(direccion=otra, nombre="Ajeno")
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:bien_detalle", args=[ajeno.pk])).status_code, 404)
        UserAppRole.objects.filter(user=self.user).update(permissions_list=["has_access_module", "can_view_oficios", "can_view_loans"])
        detalle = self.client.get(reverse("seguimientos_oficios:bien_detalle", args=[self.starlink.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertNotContains(detalle, reverse("seguimientos_oficios:bien_editar", args=[self.starlink.pk]))
        self.assertIn(self.client.get(reverse("seguimientos_oficios:bien_editar", args=[self.starlink.pk])).status_code, (302, 403))

    def test_la_migracion_rellena_la_bitacora_de_lo_anterior(self):
        import importlib

        from django.apps import apps as django_apps

        documento, prestamo = self.vale([self.starlink])
        HistorialBien.objects.all()._raw_delete(HistorialBien.objects.db)
        migracion = importlib.import_module("satelites.seguimientos_oficios.migrations.0024_bitacora_de_bienes")
        migracion.rellenar_bitacora(django_apps, None)
        self.assertEqual(self.entradas(self.starlink), ["alta", "prestamo"])
        self.assertEqual(self.starlink.historial.get(accion="prestamo").datos["folio"], documento.folio)
        self.assertEqual(self.starlink.historial.first().usuario_nombre, "Anterior a la bitácora")
