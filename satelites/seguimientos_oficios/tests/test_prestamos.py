import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.security.models import Dependencia, UserAppRole
from satelites.seguimientos_oficios.models import Bien, Direccion, Documento, Nomenclatura, Prestamo, PrestamoBien
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.prestamos.services import crear_vale, registrar_devolucion
from satelites.seguimientos_oficios.services import cancelar_documento, crear_documento

from .base import BaseAdjuntos

HOY = datetime.date(2026, 9, 20)


class PrestamosBase(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        Direccion.objects.filter(pk=self.direccion.pk).update(vales_habilitados=True)
        self.direccion.refresh_from_db()
        Nomenclatura.objects.create(direccion=self.direccion, clase="vale_prestamo", plantilla="VP-IN-{n:03d}/{anio}")
        UserAppRole.objects.filter(user=self.user).update(role="prestamos", permissions_list=P.ROLE_MAPPING["prestamos"])
        self.egresos = Dependencia.objects.create(nombre="Egresos")
        self.starlink = self.bien("Starlink", "SL-001", "INV-100")
        self.laptop = self.bien("Laptop", "LT-77")
        self.client.force_login(self.user)

    def bien(self, nombre, serie="", inventario="", direccion=None):
        return Bien.objects.create(direccion=direccion or self.direccion, nombre=nombre, identificador=serie, folio_inventario=inventario)

    def vale(self, bienes=None, limite=None, **extra):
        return crear_vale(
            usuario=self.user, direccion=self.direccion, bienes=bienes or [self.starlink],
            fecha_entrega=HOY, fecha_limite=limite or HOY + datetime.timedelta(days=7),
            contraparte=self.egresos.nombre, contraparte_dependencia_uuid=self.egresos.pk, **extra,
        )


class ValeServiceTests(PrestamosBase):
    def test_generar_un_vale_crea_documento_con_folio_automatico_y_saca_los_bienes(self):
        documento, prestamo = self.vale([self.starlink, self.laptop])
        self.assertEqual((documento.clase, documento.sentido, documento.estado), ("vale_prestamo", "enviado", "generado"))
        self.assertEqual(documento.folio, "VP-IN-001/2026")
        self.assertFalse(documento.folio_manual)
        self.assertEqual(prestamo.renglones.filter(abierto=True).count(), 2)
        self.assertIn("Starlink", documento.asunto)
        entrada = documento.historial.filter(accion="prestamo").get()
        self.assertEqual(sorted(entrada.datos["bienes"]), ["Laptop · LT-77", "Starlink · SL-001"])
        self.assertEqual(self.vale([self.bien("Proyector")])[0].folio, "VP-IN-002/2026")

    def test_un_bien_prestado_no_se_puede_prestar_otra_vez(self):
        self.vale([self.starlink])
        with self.assertRaises(ValidationError):
            self.vale([self.starlink])
        with self.assertRaises(IntegrityError), transaction.atomic():
            PrestamoBien.objects.create(prestamo=Prestamo.objects.first(), bien=self.starlink)
            PrestamoBien.objects.create(prestamo=Prestamo.objects.first(), bien=self.starlink, abierto=True)

    def test_validaciones_del_vale(self):
        otra = Direccion.objects.create(nombre="Egresos", folio_manual=False, vales_habilitados=True)
        ajeno = self.bien("Ajeno", direccion=otra)
        Bien.objects.filter(pk=self.laptop.pk).update(estado="en_reparacion")
        for bienes in ([], [ajeno], [Bien.objects.get(pk=self.laptop.pk)]):
            with self.assertRaises(ValidationError):
                self.vale(bienes) if bienes else crear_vale(
                    usuario=self.user, direccion=self.direccion, bienes=[], fecha_entrega=HOY,
                    fecha_limite=HOY, contraparte="X",
                )
        with self.assertRaises(ValidationError):
            self.vale(limite=HOY - datetime.timedelta(days=1))
        Direccion.objects.filter(pk=self.direccion.pk).update(vales_habilitados=False)
        self.direccion.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.vale()
        self.assertEqual(Documento.objects.filter(clase="vale_prestamo").count(), 0)

    def test_sin_nomenclatura_de_vale_no_se_genera_y_no_deja_nada_a_medias(self):
        Nomenclatura.objects.filter(direccion=self.direccion, clase="vale_prestamo").delete()
        with self.assertRaises(ValidationError):
            self.vale()
        self.assertEqual((Documento.objects.filter(clase="vale_prestamo").count(), Prestamo.objects.count()), (0, 0))

    def test_devolucion_completa_libera_los_bienes(self):
        documento, prestamo = self.vale([self.starlink, self.laptop])
        with mock.patch("django.utils.timezone.localdate", return_value=HOY + datetime.timedelta(days=3)):
            registrar_devolucion(prestamo, usuario=self.user, fecha=HOY + datetime.timedelta(days=2), observaciones="Todo bien")
        prestamo.refresh_from_db()
        self.assertEqual((prestamo.fecha_devolucion, prestamo.situacion), (HOY + datetime.timedelta(days=2), "devuelto"))
        self.assertFalse(prestamo.renglones.filter(abierto=True).exists())
        self.assertEqual(documento.historial.filter(accion="prestamo").last().datos["observaciones"], "Todo bien")
        self.vale([self.starlink])  # ya se puede volver a prestar

    def test_devolucion_valida_fechas_y_no_se_repite(self):
        _, prestamo = self.vale()
        with mock.patch("django.utils.timezone.localdate", return_value=HOY):
            for fecha in (HOY - datetime.timedelta(days=1), HOY + datetime.timedelta(days=1)):
                with self.assertRaises(ValidationError):
                    registrar_devolucion(prestamo, usuario=self.user, fecha=fecha)
            registrar_devolucion(prestamo, usuario=self.user, fecha=HOY)
            with self.assertRaises(ValidationError):
                registrar_devolucion(prestamo, usuario=self.user, fecha=HOY)

    def test_cancelar_el_vale_libera_los_bienes(self):
        documento, prestamo = self.vale([self.starlink])
        cancelar_documento(documento, usuario=self.user, motivo="Se prestó el bien equivocado")
        self.assertFalse(prestamo.renglones.filter(abierto=True).exists())
        self.assertEqual(documento.historial.last().datos["bienes_liberados"], ["Starlink · SL-001"])
        prestamo.refresh_from_db()
        self.assertEqual(prestamo.situacion, "cancelado")
        with self.assertRaises(ValidationError):
            registrar_devolucion(prestamo, usuario=self.user)
        self.vale([self.starlink])

    def test_situacion_segun_la_fecha_limite(self):
        _, prestamo = self.vale(limite=HOY + datetime.timedelta(days=10))
        casos = ((HOY, "vigente"), (HOY + datetime.timedelta(days=8), "por_vencer"), (HOY + datetime.timedelta(days=10), "por_vencer"), (HOY + datetime.timedelta(days=13), "vencido"))
        for hoy, esperado in casos:
            with mock.patch("django.utils.timezone.localdate", return_value=hoy):
                prestamo = Prestamo.objects.get(pk=prestamo.pk)
                self.assertEqual(prestamo.situacion, esperado, hoy)
        with mock.patch("django.utils.timezone.localdate", return_value=HOY + datetime.timedelta(days=13)):
            self.assertEqual(Prestamo.objects.get(pk=prestamo.pk).dias_de_retraso, 3)


class InterruptorPorDireccionTests(PrestamosBase):
    def test_con_vales_habilitados_el_registro_generico_no_crea_vales(self):
        with self.assertRaises(ValidationError):
            crear_documento(
                usuario=self.user, direccion=self.direccion, sentido="enviado", clase="vale_prestamo",
                contraparte="X", asunto="A mano", fecha=HOY, folio="X-1",
            )

    def test_sin_vales_habilitados_todo_sigue_como_antes_y_no_hay_pantallas_de_prestamos(self):
        Direccion.objects.filter(pk=self.direccion.pk).update(vales_habilitados=False, folio_manual=True)
        self.direccion.refresh_from_db()
        documento = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="vale_prestamo",
            contraparte="X", asunto="Vale manual", fecha=HOY, folio="V-1",
        )
        self.assertEqual(documento.folio, "V-1")
        self.assertContains(self.client.get(reverse("seguimientos_oficios:vale_crear")), "tiene habilitados los vales de préstamo")
        self.assertEqual(len(self.client.get(reverse("seguimientos_oficios:bienes")).context["pagina"]), 0)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:bien_crear")), "tiene habilitados los vales de préstamo")

    def test_el_interruptor_se_administra_en_catalogos(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        url = reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk])
        self.assertContains(self.client.get(url), "Vales de préstamo")
        self.client.post(url, {"nombre": self.direccion.nombre, "dependencia": str(self.dep.pk), "is_active": "on"})
        self.direccion.refresh_from_db()
        self.assertFalse(self.direccion.vales_habilitados)
        self.client.post(url, {"nombre": self.direccion.nombre, "dependencia": str(self.dep.pk), "is_active": "on", "vales_habilitados": "on"})
        self.direccion.refresh_from_db()
        self.assertTrue(self.direccion.vales_habilitados)

    def test_no_se_ve_lo_de_direcciones_sin_vales_ni_de_otras_direcciones(self):
        otra = Direccion.objects.create(nombre="Egresos", folio_manual=False, vales_habilitados=True)
        self.bien("Bien ajeno", direccion=otra)
        pagina = self.client.get(reverse("seguimientos_oficios:bienes"))
        self.assertNotContains(pagina, "Bien ajeno")
        self.assertContains(pagina, "Starlink")


class VistasPrestamosTests(PrestamosBase):
    def test_generar_el_vale_desde_el_formulario_y_ver_todo(self):
        respuesta = self.client.post(reverse("seguimientos_oficios:vale_crear"), {
            "direccion": str(self.direccion.pk), "contraparte_dependencia": str(self.egresos.pk), "contraparte": "",
            "fecha_entrega": "2026-09-20", "fecha_limite": "2026-09-30", "bienes": [str(self.starlink.pk)],
            "gestor": "", "observaciones": "Para junta",
        })
        documento = Documento.objects.get(clase="vale_prestamo")
        self.assertRedirects(respuesta, reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        detalle = self.client.get(respuesta.url)
        self.assertContains(detalle, "Registrar devolución")
        self.assertContains(detalle, "Imprimir vale")
        self.assertContains(detalle, "Starlink")
        lista = self.client.get(reverse("seguimientos_oficios:prestamos"))
        self.assertContains(lista, documento.folio)
        self.assertEqual({t["clave"]: t["total"] for t in lista.context["tabs"]}["abiertos"], 1)
        formulario = self.client.get(reverse("seguimientos_oficios:vale_crear"))
        self.assertNotContains(formulario, "Starlink")
        self.assertContains(formulario, "Laptop")

    def test_el_formulario_rechaza_bienes_ya_prestados_y_fechas_invertidas(self):
        self.vale([self.starlink])
        base = {
            "direccion": str(self.direccion.pk), "contraparte_dependencia": str(self.egresos.pk), "contraparte": "",
            "fecha_entrega": "2026-09-20", "fecha_limite": "2026-09-30", "gestor": "", "observaciones": "",
        }
        url = reverse("seguimientos_oficios:vale_crear")
        self.assertEqual(self.client.post(url, {**base, "bienes": [str(self.starlink.pk)]}).status_code, 200)
        self.assertEqual(self.client.post(url, {**base, "fecha_limite": "2026-09-01", "bienes": [str(self.laptop.pk)]}).status_code, 200)
        self.assertEqual(self.client.post(url, {**base, "contraparte_dependencia": "", "bienes": [str(self.laptop.pk)]}).status_code, 200)
        self.assertEqual(Documento.objects.filter(clase="vale_prestamo").count(), 1)

    def test_devolucion_desde_el_detalle(self):
        documento, prestamo = self.vale()
        with mock.patch("django.utils.timezone.localdate", return_value=HOY):
            self.client.post(reverse("seguimientos_oficios:vale_devolucion", args=[documento.pk]), {"fecha": "2026-09-20", "observaciones": "Completo"})
        prestamo.refresh_from_db()
        self.assertIsNotNone(prestamo.fecha_devolucion)
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertNotContains(detalle, "Registrar devolución")
        self.assertContains(detalle, "Devolución completa")

    def test_pagina_imprimible_del_vale(self):
        documento, _ = self.vale([self.starlink, self.laptop])
        pagina = self.client.get(reverse("seguimientos_oficios:vale_imprimir", args=[documento.pk]))
        for texto in (documento.folio, "Starlink", "SL-001", "INV-100", "Laptop", "Vale de préstamo", "Recibe"):
            self.assertContains(pagina, texto)

    def test_bienes_alta_edicion_duplicados_y_situacion(self):
        crear = reverse("seguimientos_oficios:bien_crear")
        datos = {"direccion": str(self.direccion.pk), "nombre": "Router", "identificador": "R-1", "folio_inventario": "INV-100", "descripcion": "", "estado": "disponible"}
        self.assertEqual(self.client.post(crear, datos).status_code, 200)
        self.assertFalse(Bien.objects.filter(nombre="Router").exists())
        self.assertEqual(self.client.post(crear, {**datos, "folio_inventario": "INV-200"}).status_code, 302)
        router = Bien.objects.get(nombre="Router")
        editar = reverse("seguimientos_oficios:bien_editar", args=[router.pk])
        self.client.post(editar, {**datos, "nombre": "Router principal", "folio_inventario": "INV-200", "estado": "en_reparacion"})
        router.refresh_from_db()
        self.assertEqual((router.nombre, router.estado), ("Router principal", "en_reparacion"))
        self.vale([self.starlink])
        self.client.post(reverse("seguimientos_oficios:bien_editar", args=[self.starlink.pk]), {**datos, "nombre": "Starlink", "identificador": "SL-001", "folio_inventario": "INV-100", "estado": "baja"})
        self.starlink.refresh_from_db()
        self.assertEqual(self.starlink.estado, "disponible")
        lista = self.client.get(reverse("seguimientos_oficios:bienes"))
        self.assertContains(lista, "Prestado")
        self.assertContains(lista, "hasta el 27/09/26")
        solo_prestados = self.client.get(reverse("seguimientos_oficios:bienes"), {"situacion": "prestado"})
        self.assertEqual([b.nombre for b in solo_prestados.context["pagina"]], ["Starlink"])
        self.assertEqual([b.nombre for b in self.client.get(reverse("seguimientos_oficios:bienes"), {"q": "lt-77"}).context["pagina"]], ["Laptop"])

    def test_solo_el_rol_de_prestamos_ve_el_menu_y_las_pantallas(self):
        UserAppRole.objects.filter(user=self.user).update(role="editor", permissions_list=P.ROLE_MAPPING["editor"])
        for nombre in ("prestamos", "bienes", "vale_crear", "bien_crear"):
            self.assertIn(self.client.get(reverse(f"seguimientos_oficios:{nombre}")).status_code, (302, 403), nombre)
        menu = self.client.get(reverse("seguimientos_oficios:documento_list"))
        self.assertNotContains(menu, reverse("seguimientos_oficios:prestamos"))
        UserAppRole.objects.filter(user=self.user).update(role="prestamos", permissions_list=P.ROLE_MAPPING["prestamos"])
        menu = self.client.get(reverse("seguimientos_oficios:documento_list"))
        self.assertContains(menu, reverse("seguimientos_oficios:prestamos"))
        self.assertContains(menu, reverse("seguimientos_oficios:bienes"))

    def test_quien_solo_consulta_no_puede_generar_ni_devolver(self):
        documento, prestamo = self.vale()
        UserAppRole.objects.filter(user=self.user).update(permissions_list=["has_access_module", "can_view_oficios", "can_view_loans"])
        self.assertIn(self.client.get(reverse("seguimientos_oficios:vale_crear")).status_code, (302, 403))
        self.client.post(reverse("seguimientos_oficios:vale_devolucion", args=[documento.pk]), {"fecha": ""})
        prestamo.refresh_from_db()
        self.assertIsNone(prestamo.fecha_devolucion)
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])), "Registrar devolución")
