import datetime
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.seguimientos_oficios.models import Adjunto, Direccion, Gestor, Nomenclatura
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento, marcar_entregado

# Lo que el editor podía hacer antes de sumarle préstamos y soporte técnico: sirve para probar a quien solo lleva oficios.
SOLO_OFICIOS = [p for p in P.ROLE_MAPPING["editor"] if p not in ("can_view_loans", "can_manage_loans", "can_view_support", "can_manage_support")]

PDF = b"%PDF-1.4\n%contenido de prueba\n"


def pdf(nombre="oficio.pdf", contenido=PDF):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
)
class BaseAdjuntos(TestCase):
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
        cls.direccion = Direccion.objects.create(nombre="Innovación", dependencia_uuid=cls.dep.pk, folio_manual=False)
        Nomenclatura.objects.create(direccion=cls.direccion, clase="oficio", plantilla="IN-{n:03d}/{anio}")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.override = override_settings(OFICIOS_ARCHIVOS_ROOT=self._tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def gestor(self, nombre, direccion=None):
        """Gestor de prueba: un usuario real con membresía y rol `gestor`, vinculado a la dirección."""
        usuario = get_user_model().objects.create_user(
            email=f"{nombre.lower().replace(' ', '.')}@gestores.test", first_name=nombre
        )
        UserAppRole.objects.create(user=usuario, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        return Gestor.objects.create(direccion=direccion or self.direccion, usuario=usuario)

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

