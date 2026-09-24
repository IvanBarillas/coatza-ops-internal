import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import AdjuntoOCR, Direccion
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_pdf, cancelar_documento, quitar_adjunto

from .base import PDF, BaseAdjuntos, pdf

MOTIVO = "Se subió el archivo equivocado por error"


class QuitarArchivosTests(BaseAdjuntos):
    def adjuntar(self, documento, nombre="a.pdf", extra=b"", rol=None):
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, duplicado = adjuntar_pdf(documento, usuario=self.user, archivo=pdf(nombre, PDF + extra), rol=rol)
        return adjunto, duplicado

    def test_quitar_lo_oculta_lo_bloquea_y_deja_historial(self):
        documento = self.documento()
        adjunto, _ = self.adjuntar(documento)
        quitar_adjunto(adjunto, usuario=self.user, motivo=MOTIVO)
        adjunto.refresh_from_db()
        self.assertTrue(adjunto.eliminado)
        self.assertEqual(adjunto.eliminado_motivo, MOTIVO)
        entrada = documento.historial.last()
        self.assertEqual((entrada.accion, entrada.datos["motivo"], entrada.datos["adjunto"]), ("quitado", MOTIVO, "a.pdf"))
        self.client.force_login(self.user)
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertContains(detalle, "Archivos quitados (1)")
        self.assertContains(detalle, MOTIVO)
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk])).status_code, 404)

    def test_motivo_obligatorio_y_no_se_quita_dos_veces(self):
        adjunto, _ = self.adjuntar(self.documento())
        for motivo in ("", "corto", "   "):
            with self.assertRaises(ValidationError):
                quitar_adjunto(adjunto, usuario=self.user, motivo=motivo)
        quitar_adjunto(adjunto, usuario=self.user, motivo=MOTIVO)
        with self.assertRaises(ValidationError):
            quitar_adjunto(adjunto, usuario=self.user, motivo=MOTIVO)

    def test_quitar_la_unica_evidencia_regresa_el_documento_a_entregado(self):
        documento = self.entregado()
        evidencia, _ = self.adjuntar(documento)
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "concluido")
        quitar_adjunto(evidencia, usuario=self.user, motivo=MOTIVO)
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "entregado")
        self.assertEqual(documento.historial.last().datos["estado_nuevo"], "entregado")
        nueva, _ = self.adjuntar(documento, "correcta.pdf", b"otra")
        documento.refresh_from_db()
        self.assertEqual((nueva.rol, documento.estado), ("evidencia", "concluido"))

    def test_con_otra_evidencia_vigente_sigue_concluido_y_quitar_un_firmado_no_cambia_estado(self):
        documento = self.entregado()
        primera, _ = self.adjuntar(documento, "e1.pdf", b"1")
        self.adjuntar(documento, "e2.pdf", b"2", rol="evidencia")
        firmado, _ = self.adjuntar(documento, "f.pdf", b"f", rol="firmado")
        quitar_adjunto(primera, usuario=self.user, motivo=MOTIVO)
        quitar_adjunto(firmado, usuario=self.user, motivo=MOTIVO)
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "concluido")

    def test_cancelado_no_admite_quitar(self):
        documento = self.documento()
        adjunto, _ = self.adjuntar(documento)
        cancelar_documento(documento, usuario=self.user, motivo="Registrado por error en la captura")
        with self.assertRaises(ValidationError):
            quitar_adjunto(adjunto, usuario=self.user, motivo=MOTIVO)

    def test_lo_quitado_sale_de_la_busqueda_y_no_cuenta_como_duplicado(self):
        documento = self.documento("recibido")
        adjunto, _ = self.adjuntar(documento)
        ocr = AdjuntoOCR.objects.get(adjunto=adjunto)
        ocr.estado, ocr.texto = "listo", "texto muy particular zorrillo"
        ocr.save()
        self.client.force_login(self.user)
        buscar = lambda q: self.client.get(reverse("seguimientos_oficios:busqueda"), {"q": q})
        self.assertContains(buscar("zorrillo"), "Pág. 1")
        quitar_adjunto(adjunto, usuario=self.user, motivo=MOTIVO)
        self.assertContains(buscar("zorrillo"), "Sin resultados")
        otro = self.documento("recibido")
        _, duplicado = self.adjuntar(otro)
        self.assertIsNone(duplicado)

    def test_vista_exige_permiso_y_respeta_el_alcance(self):
        documento = self.documento()
        adjunto, _ = self.adjuntar(documento)
        url = reverse("seguimientos_oficios:adjunto_quitar", args=[documento.pk, adjunto.pk])
        UserAppRole.objects.filter(user=self.user).update(role="viewer", permissions_list=P.ROLE_MAPPING["viewer"])
        self.client.force_login(self.user)
        self.assertIn(self.client.post(url, {"motivo": MOTIVO}).status_code, (302, 403))
        adjunto.refresh_from_db()
        self.assertFalse(adjunto.eliminado)
        UserAppRole.objects.filter(user=self.user).update(role="editor", permissions_list=P.ROLE_MAPPING["editor"])
        self.client.post(url, {"motivo": MOTIVO})
        adjunto.refresh_from_db()
        self.assertTrue(adjunto.eliminado)

    def test_no_se_quita_en_documentos_de_otra_direccion(self):
        otra = Direccion.objects.create(nombre="Egresos")
        from satelites.seguimientos_oficios.models import Documento

        ajeno = Documento.objects.create(
            sentido="recibido", estado="registrado", direccion=otra, direccion_nombre="Egresos",
            contraparte="X", asunto="Ajeno", fecha=datetime.date(2026, 9, 1),
        )
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:adjunto_quitar", args=[ajeno.pk, ajeno.pk])
        self.assertEqual(self.client.post(url, {"motivo": MOTIVO}).status_code, 404)
