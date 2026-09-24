import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios import bandeja
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_desde_bandeja, listar_bandeja, marcar_entregado

from .base import PDF, BaseAdjuntos


class BandejaTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self._raiz = tempfile.TemporaryDirectory()
        self.addCleanup(self._raiz.cleanup)
        self.raiz = Path(self._raiz.name).resolve()
        override = override_settings(OFICIOS_BANDEJA_RAIZ=str(self.raiz))
        override.enable()
        self.addCleanup(override.disable)
        (self.raiz / "innovacion" / "recibidos").mkdir(parents=True)
        (self.raiz / "innovacion" / "evidencias").mkdir(parents=True)
        self.direccion.ruta_recibidos = "innovacion/recibidos"
        self.direccion.ruta_evidencias = "innovacion/evidencias"
        self.direccion.ruta_firmados = "innovacion/firmados"
        (self.raiz / "innovacion" / "firmados").mkdir()
        self.direccion.save()

    def escanear(self, carpeta, nombre="scan.pdf", contenido=PDF):
        ruta = self.raiz / "innovacion" / carpeta / nombre
        ruta.write_bytes(contenido)
        return ruta

    def test_resolver_rechaza_salidas_de_la_raiz(self):
        for mala in ("../fuera", "innovacion/../../fuera", "no/existe"):
            with self.assertRaises(bandeja.BandejaError):
                bandeja.resolver(mala)
        fuera = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, fuera)
        os.symlink(fuera, self.raiz / "enlace")
        with self.assertRaises(bandeja.BandejaError):
            bandeja.resolver("enlace")

    def test_resolver_exige_raiz_definida(self):
        with override_settings(OFICIOS_BANDEJA_RAIZ=""), mock.patch("core.settings.base.config", return_value=""):
            with self.assertRaises(bandeja.BandejaError):
                bandeja.resolver("innovacion")

    def test_listado_solo_pdfs_sin_recursion_ocultos_ni_enlaces(self):
        self.escanear("recibidos", "bueno.PDF")
        self.escanear("recibidos", "nota.txt", b"x")
        self.escanear("recibidos", ".oculto.pdf")
        (self.raiz / "innovacion" / "recibidos" / "sub").mkdir()
        self.escanear("recibidos/sub", "profundo.pdf")
        os.symlink(self.raiz / "innovacion" / "recibidos" / "bueno.PDF", self.raiz / "innovacion" / "recibidos" / "enlace.pdf")
        nombres = [a["nombre"] for a in bandeja.listar_pdfs(self.raiz / "innovacion" / "recibidos")]
        self.assertEqual(nombres, ["bueno.PDF"])

    def test_adjuntar_recibido_desde_bandeja_y_archivar(self):
        documento = self.documento("recibido")
        origen = self.escanear("recibidos")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            with self.captureOnCommitCallbacks(execute=True):
                adjunto, _ = adjuntar_desde_bandeja(documento, usuario=self.user, nombre="scan.pdf")
        self.assertEqual(adjunto.rol, "original")
        self.assertEqual(documento.historial.last().datos["origen"], "bandeja")
        self.assertFalse(origen.exists())
        self.assertEqual(len(list((self.raiz / "innovacion" / "recibidos" / "procesados").rglob("scan.pdf"))), 1)

    def test_enviado_usa_la_carpeta_de_evidencias(self):
        documento = self.entregado()
        self.escanear("recibidos", "no-es-esta.pdf")
        self.escanear("evidencias", "acuse.pdf")
        self.assertEqual([a["nombre"] for a in listar_bandeja(documento)], ["acuse.pdf"])
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_desde_bandeja(documento, usuario=self.user, nombre="acuse.pdf")
        documento.refresh_from_db()
        self.assertEqual((adjunto.rol, documento.estado), ("evidencia", "concluido"))

    def test_nombre_con_ruta_o_inexistente_se_rechaza(self):
        documento = self.documento("recibido")
        self.escanear("recibidos")
        (self.raiz / "secreto.pdf").write_bytes(PDF)
        for nombre in ("../../secreto.pdf", "/etc/passwd", "no-existe.pdf", "scan.txt", ""):
            with self.assertRaises(ValidationError):
                adjuntar_desde_bandeja(documento, usuario=self.user, nombre=nombre)

    def test_sin_carpeta_configurada_da_error_claro(self):
        self.direccion.ruta_recibidos = ""
        self.direccion.save()
        with self.assertRaises(ValidationError):
            listar_bandeja(self.documento("recibido"))

    def test_archivo_no_pdf_disfrazado_no_se_adjunta_ni_se_mueve(self):
        documento = self.documento("recibido")
        origen = self.escanear("recibidos", "falso.pdf", b"<html>no</html>")
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValidationError):
                adjuntar_desde_bandeja(documento, usuario=self.user, nombre="falso.pdf")
        self.assertTrue(origen.exists())

    def test_vistas_de_configuracion_exigen_permiso_y_guardan(self):
        self.client.force_login(self.user)
        self.assertIn(self.client.get(reverse("seguimientos_oficios:configuracion")).status_code, (302, 403))
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        respuesta = self.client.get(reverse("seguimientos_oficios:configuracion"))
        self.assertContains(respuesta, "innovacion/recibidos")
        url = reverse("seguimientos_oficios:configuracion_guardar", args=[self.direccion.pk])
        self.client.post(url, {"ruta_recibidos": "../fuera", "ruta_evidencias": "innovacion/evidencias"})
        self.direccion.refresh_from_db()
        self.assertEqual(self.direccion.ruta_recibidos, "innovacion/recibidos")
        (self.raiz / "innovacion" / "nueva").mkdir()
        self.client.post(url, {"ruta_recibidos": "/innovacion/nueva/", "ruta_evidencias": ""})
        self.direccion.refresh_from_db()
        self.assertEqual((self.direccion.ruta_recibidos, self.direccion.ruta_evidencias), ("innovacion/nueva", ""))

    def test_vista_de_bandeja_lista_y_adjunta(self):
        documento = self.documento("recibido")
        self.escanear("recibidos")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_bandeja", args=[documento.pk])), "scan.pdf")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            self.client.post(reverse("seguimientos_oficios:documento_adjuntar_bandeja", args=[documento.pk]), {"nombre": "scan.pdf"})
        self.assertEqual(documento.adjuntos.count(), 1)

    def test_generado_toma_el_firmado_de_su_carpeta_y_no_concluye(self):
        documento = self.documento()
        self.escanear("firmados", "oficio-firmado.pdf")
        self.escanear("evidencias", "acuse.pdf")
        self.assertEqual([a["nombre"] for a in listar_bandeja(documento)], ["oficio-firmado.pdf"])
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_desde_bandeja(documento, usuario=self.user, nombre="oficio-firmado.pdf")
        documento.refresh_from_db()
        self.assertEqual((adjunto.rol, documento.estado), ("firmado", "generado"))
        with self.assertRaises(ValidationError):
            adjuntar_desde_bandeja(documento, usuario=self.user, nombre="acuse.pdf", rol="evidencia")

    def test_entregado_elige_la_carpeta_segun_el_tipo(self):
        documento = self.entregado()
        self.escanear("firmados", "f.pdf")
        self.escanear("evidencias", "e.pdf")
        self.assertEqual([a["nombre"] for a in listar_bandeja(documento)], ["e.pdf"])
        self.assertEqual([a["nombre"] for a in listar_bandeja(documento, "firmado")], ["f.pdf"])

    def test_sin_carpeta_de_firmados_da_error_claro(self):
        self.direccion.ruta_firmados = ""
        self.direccion.save()
        with self.assertRaises(ValidationError):
            listar_bandeja(self.documento())

    def test_vista_de_bandeja_usa_el_tipo_pedido(self):
        documento = self.entregado()
        self.escanear("firmados", "solo-firmado.pdf")
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:documento_bandeja", args=[documento.pk])
        self.assertContains(self.client.get(url, {"rol": "firmado"}), "solo-firmado.pdf")
        self.assertNotContains(self.client.get(url, {"rol": "evidencia"}), "solo-firmado.pdf")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            self.client.post(reverse("seguimientos_oficios:documento_adjuntar_bandeja", args=[documento.pk]),
                             {"nombre": "solo-firmado.pdf", "rol": "firmado"})
        self.assertEqual(documento.adjuntos.get().rol, "firmado")

    def test_configuracion_guarda_la_carpeta_de_firmados(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:configuracion_guardar", args=[self.direccion.pk])
        self.client.post(url, {"ruta_recibidos": "innovacion/recibidos", "ruta_firmados": "innovacion/firmados", "ruta_evidencias": ""})
        self.direccion.refresh_from_db()
        self.assertEqual((self.direccion.ruta_firmados, self.direccion.ruta_evidencias), ("innovacion/firmados", ""))
        self.assertContains(self.client.get(reverse("seguimientos_oficios:configuracion")), "Firmados")

    def test_la_configuracion_no_muestra_la_ruta_del_servidor_ni_habla_de_qnap(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.force_login(self.user)
        pagina = self.client.get(reverse("seguimientos_oficios:configuracion"))
        self.assertNotContains(pagina, str(self.raiz))
        self.assertNotContains(pagina, "QNAP")
        self.assertContains(pagina, "innovacion/oficios/recibidos")
