import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from satelites.seguimientos_oficios.models import ConsecutivoFolio, Direccion, Documento
from satelites.seguimientos_oficios.services import crear_documento, editar_documento

from .base import BaseAdjuntos


class FolioManualTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        Direccion.objects.filter(pk=self.direccion.pk).update(folio_manual=True)
        self.direccion.refresh_from_db()
        self.client.force_login(self.user)

    def enviar(self, folio="", **extra):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="Tesorería", asunto="Asunto", fecha=datetime.date(2026, 9, 1), folio=folio, **extra,
        )

    def test_enviado_usa_el_folio_escrito_y_no_genera_uno(self):
        documento = self.enviar("DGD/045/2026")
        self.assertEqual((documento.folio, documento.folio_manual, documento.estado), ("DGD/045/2026", True, "generado"))
        self.assertFalse(ConsecutivoFolio.objects.exists())

    def test_folio_obligatorio_y_no_se_repite_en_la_direccion(self):
        with self.assertRaises(ValidationError):
            self.enviar("  ")
        self.enviar("DGD/1/2026")
        with self.assertRaises(ValidationError):
            self.enviar("DGD/1/2026")
        cancelado = Documento.objects.get(folio="DGD/1/2026")
        Documento.objects.filter(pk=cancelado.pk).update(estado="cancelado")
        with self.assertRaises(ValidationError):
            self.enviar("DGD/1/2026")

    def test_si_el_folio_sigue_la_nomenclatura_el_contador_continua_desde_ahi(self):
        self.enviar("IN-045/2026")
        self.assertEqual(ConsecutivoFolio.objects.get().ultimo, 45)
        Direccion.objects.filter(pk=self.direccion.pk).update(folio_manual=False)
        self.direccion.refresh_from_db()
        self.assertEqual(self.enviar().folio, "IN-046/2026")

    def test_con_folio_automatico_se_ignora_lo_escrito(self):
        Direccion.objects.filter(pk=self.direccion.pk).update(folio_manual=False)
        self.direccion.refresh_from_db()
        documento = self.enviar("LO-QUE-SEA")
        self.assertEqual((documento.folio, documento.folio_manual), ("IN-001/2026", False))

    def test_el_formulario_pide_el_folio_de_enviados_y_lo_guarda(self):
        url = reverse("seguimientos_oficios:documento_create")
        datos = {
            "sentido": "enviado", "clase": "oficio", "direccion": str(self.direccion.pk), "fecha": "2026-09-02",
            "contraparte": "Tesorería", "asunto": "Con folio manual", "folio": "",
        }
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, "Escriba el folio del oficio.")
        self.assertFalse(Documento.objects.filter(asunto="Con folio manual").exists())
        datos["folio"] = "DGD/046/2026"
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertEqual(Documento.objects.get(asunto="Con folio manual").folio, "DGD/046/2026")
        repetido = self.client.post(url, {**datos, "asunto": "Repetido"})
        self.assertContains(repetido, "Ya existe un oficio enviado con el folio DGD/046/2026")

    def test_se_puede_corregir_un_folio_manual_pero_no_uno_generado(self):
        manual = self.enviar("DGD/9/2026")
        editar_documento(manual, usuario=self.user, cambios={"folio": "DGD/09/2026"})
        manual.refresh_from_db()
        self.assertEqual(manual.folio, "DGD/09/2026")
        self.assertEqual(manual.historial.last().datos["cambios"]["folio"], {"antes": "DGD/9/2026", "despues": "DGD/09/2026"})
        otro = self.enviar("DGD/10/2026")
        with self.assertRaises(ValidationError):
            editar_documento(otro, usuario=self.user, cambios={"folio": "DGD/09/2026"})
        with self.assertRaises(ValidationError):
            editar_documento(otro, usuario=self.user, cambios={"folio": ""})
        Direccion.objects.filter(pk=self.direccion.pk).update(folio_manual=False)
        self.direccion.refresh_from_db()
        automatico = self.enviar()
        with self.assertRaises(ValidationError):
            editar_documento(automatico, usuario=self.user, cambios={"folio": "OTRO"})

    def test_pantalla_de_edicion_ofrece_folio_solo_si_es_manual(self):
        manual = self.enviar("DGD/11/2026")
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_editar", args=[manual.pk])), 'name="folio"')
        Direccion.objects.filter(pk=self.direccion.pk).update(folio_manual=False)
        self.direccion.refresh_from_db()
        automatico = self.enviar()
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:documento_editar", args=[automatico.pk])), 'name="folio"')

    def test_el_ajuste_se_administra_en_catalogos(self):
        from apps.security.models import UserAppRole
        from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P

        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        url = reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk])
        self.assertContains(self.client.get(url), "Folio manual")
        self.client.post(url, {"nombre": self.direccion.nombre, "dependencia": str(self.dep.pk), "is_active": "on"})
        self.direccion.refresh_from_db()
        self.assertFalse(self.direccion.folio_manual)
