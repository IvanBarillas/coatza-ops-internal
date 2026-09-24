from django.core.exceptions import ValidationError
from django.urls import reverse

from satelites.seguimientos_oficios.models import Adjunto, Direccion
from satelites.seguimientos_oficios.storage import almacen
from satelites.seguimientos_oficios.services import adjuntar_pdf

from .base import PDF, AreaOperativa, BaseAdjuntos, Dependencia, Sede, UserProfile, pdf


class AdjuntosTests(BaseAdjuntos):
    def test_evidencia_concluye_el_documento(self):
        documento = self.entregado()
        adjunto, duplicado = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        documento.refresh_from_db()
        self.assertEqual((documento.estado, adjunto.rol, duplicado), ("concluido", "evidencia", None))
        self.assertEqual(documento.historial.last().datos["estado_nuevo"], "concluido")

    def test_generado_recibe_el_documento_firmado_sin_cambiar_de_estado(self):
        documento = self.documento()
        adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        documento.refresh_from_db()
        self.assertEqual((adjunto.rol, documento.estado), ("firmado", "generado"))
        self.assertRegex(adjunto.ruta, r"^2026/innovacion/enviados/IN-001-2026__firmado__")

    def test_evidencia_solo_si_ya_fue_entregado(self):
        with self.assertRaises(ValidationError):
            adjuntar_pdf(self.documento(), usuario=self.user, archivo=pdf(), rol="evidencia")

    def test_entregado_acepta_firmado_o_evidencia_y_solo_la_evidencia_concluye(self):
        documento = self.entregado()
        firmado, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf("f.pdf", PDF + b"f"), rol="firmado")
        documento.refresh_from_db()
        self.assertEqual((firmado.rol, documento.estado), ("firmado", "entregado"))
        evidencia, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf("e.pdf", PDF + b"e"))
        documento.refresh_from_db()
        self.assertEqual((evidencia.rol, documento.estado), ("evidencia", "concluido"))

    def test_roles_permitidos_por_estado(self):
        from satelites.seguimientos_oficios.services import cancelar_documento, roles_permitidos

        self.assertEqual(roles_permitidos(self.documento("recibido")), ["original"])
        self.assertEqual(roles_permitidos(self.documento()), ["firmado"])
        self.assertEqual(roles_permitidos(self.entregado()), ["evidencia", "firmado"])
        cancelado = self.documento()
        cancelar_documento(cancelado, usuario=self.user, motivo="Registrado por error en la captura")
        cancelado.refresh_from_db()
        self.assertEqual(roles_permitidos(cancelado), [])
        with self.assertRaises(ValidationError):
            adjuntar_pdf(cancelado, usuario=self.user, archivo=pdf())

    def test_el_detalle_ofrece_solo_lo_que_corresponde(self):
        self.client.force_login(self.user)
        generado = self.documento()
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[generado.pk]))
        self.assertContains(detalle, '<input type="hidden" name="rol" value="firmado">')
        self.assertContains(detalle, "Documento firmado")
        entregado = self.entregado()
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[entregado.pk]))
        self.assertContains(detalle, 'id="rol-adjunto"')
        self.assertContains(detalle, "Evidencia de entrega")

    def test_recibido_adjunta_original_sin_cambiar_estado(self):
        documento = self.documento("recibido")
        adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        documento.refresh_from_db()
        self.assertEqual((adjunto.rol, documento.estado), ("original", "registrado"))

    def test_rechaza_archivos_que_no_son_pdf(self):
        documento = self.entregado()
        with self.assertRaises(ValidationError):
            adjuntar_pdf(documento, usuario=self.user, archivo=pdf("falso.pdf", b"<html>no soy pdf</html>"))

    def test_duplicado_avisa_pero_no_bloquea_y_reusa_el_archivo(self):
        primero = self.entregado()
        a1, _ = adjuntar_pdf(primero, usuario=self.user, archivo=pdf())
        segundo = self.documento("recibido")
        a2, duplicado = adjuntar_pdf(segundo, usuario=self.user, archivo=pdf("otro-nombre.pdf"))
        self.assertEqual(duplicado.documento, primero)
        self.assertNotEqual(a1.ruta, a2.ruta)
        self.assertEqual(a1.sha256, a2.sha256)
        self.assertEqual(Adjunto.objects.count(), 2)

    def test_ruta_ordenada_por_anio_direccion_y_sentido(self):
        evidencia, _ = adjuntar_pdf(self.entregado(), usuario=self.user, archivo=pdf())
        original, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("x.pdf", PDF + b"otro"))
        self.assertRegex(evidencia.ruta, r"^2026/innovacion/enviados/IN-001-2026__evidencia__[0-9a-f]{12}\.pdf$")
        self.assertRegex(original.ruta, r"^2026/innovacion/recibidos/sin-folio__original__[0-9a-f]{12}\.pdf$")
        self.assertTrue(almacen().exists(evidencia.ruta))

    def test_slug_de_direccion_es_estable_y_unico(self):
        otra = Direccion.objects.create(nombre="Innovación!")
        self.assertEqual(self.direccion.slug, "innovacion")
        self.assertEqual(otra.slug, "innovacion-2")
        self.direccion.nombre = "Innovación y Gobierno Digital"
        self.direccion.save()
        self.direccion.refresh_from_db()
        self.assertEqual(self.direccion.slug, "innovacion")

    def test_adjunto_no_se_modifica_ni_borra(self):
        adjunto, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf())
        with self.assertRaises(ValueError):
            adjunto.save()
        with self.assertRaises(ValueError):
            adjunto.delete()

    def test_subir_y_descargar_por_las_vistas(self):
        documento = self.entregado()
        self.client.force_login(self.user)
        self.client.post(reverse("seguimientos_oficios:documento_adjuntar", args=[documento.pk]), {"archivo": pdf()})
        adjunto = documento.adjuntos.get()
        respuesta = self.client.get(reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), PDF)
        self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")

    def test_no_se_descarga_adjunto_de_otra_direccion(self):
        documento = self.entregado()
        adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        UserProfile.objects.filter(user=self.user).update(
            area=AreaOperativa.objects.create(
                nombre="Otra", dependencia=Dependencia.objects.create(nombre="Otra"), sede_fisica=Sede.objects.first()
            )
        )
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk]))
        self.assertEqual(respuesta.status_code, 404)
