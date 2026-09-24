import datetime
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.seguimientos_oficios.models import Adjunto, Direccion, Nomenclatura
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento, marcar_entregado

PDF = b"%PDF-1.4\n%contenido de prueba\n"


def pdf(nombre="oficio.pdf", contenido=PDF):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
)
class AdjuntosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app, _ = AppModule.objects.get_or_create(slug=P.APP_CODE, defaults={"name": "Oficios"})
        cls.app.is_active = True
        cls.app.save()
        cls.dep = Dependencia.objects.create(nombre="Innovación")
        area = AreaOperativa.objects.create(nombre="Oficina", dependencia=cls.dep, sede_fisica=Sede.objects.create(nombre="Palacio"))
        cls.user = get_user_model().objects.create_user(email="adj@example.test")
        UserProfile.objects.create(user=cls.user, area=area)
        UserAppRole.objects.create(user=cls.user, app=cls.app, role="editor", permissions_list=P.ROLE_MAPPING["editor"])
        cls.direccion = Direccion.objects.create(nombre="Innovación", dependencia_uuid=cls.dep.pk)
        Nomenclatura.objects.create(direccion=cls.direccion, clase="oficio", plantilla="IN-{n:03d}/{anio}")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.override = override_settings(OFICIOS_ARCHIVOS_ROOT=self._tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def documento(self, sentido="enviado"):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido=sentido, clase="oficio",
            contraparte="Tesorería", asunto="Asunto", fecha=datetime.date(2026, 9, 1),
        )

    def entregado(self):
        documento = self.documento()
        marcar_entregado(documento, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="Recepción")
        documento.refresh_from_db()
        return documento

    def test_evidencia_concluye_el_documento(self):
        documento = self.entregado()
        adjunto, duplicado = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        documento.refresh_from_db()
        self.assertEqual((documento.estado, adjunto.rol, duplicado), ("concluido", "evidencia", None))
        self.assertEqual(documento.historial.last().datos["estado_nuevo"], "concluido")

    def test_evidencia_solo_si_ya_fue_entregado(self):
        with self.assertRaises(ValidationError):
            adjuntar_pdf(self.documento(), usuario=self.user, archivo=pdf())

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
        self.assertEqual(a1.ruta, a2.ruta)
        self.assertEqual(Adjunto.objects.count(), 2)

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
