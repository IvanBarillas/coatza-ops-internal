import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import (
    AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile,
)
from satelites.seguimientos_oficios.models import Direccion, Documento
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False,
    AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
)
class VisibilidadOficiosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app, _ = AppModule.objects.get_or_create(
            slug=P.APP_CODE, defaults={"name": "Seguimiento de Oficios"}
        )
        cls.app.is_active = True
        cls.app.save()
        cls.dep_propia = Dependencia.objects.create(nombre="Innovación")
        cls.dep_ajena = Dependencia.objects.create(nombre="Egresos")
        sede = Sede.objects.create(nombre="Palacio")
        area = AreaOperativa.objects.create(nombre="Oficina", dependencia=cls.dep_propia, sede_fisica=sede)
        cls.user = get_user_model().objects.create_user(email="oficios@example.test")
        UserProfile.objects.create(user=cls.user, area=area)
        UserAppRole.objects.create(
            user=cls.user, app=cls.app, role="editor", permissions_list=P.ROLE_MAPPING["editor"]
        )
        cls.dir_propia = Direccion.objects.create(nombre="Innovación", dependencia_uuid=cls.dep_propia.pk)
        cls.dir_ajena = Direccion.objects.create(nombre="Egresos", dependencia_uuid=cls.dep_ajena.pk)
        for direccion, asunto in ((cls.dir_propia, "Oficio propio"), (cls.dir_ajena, "Oficio ajeno")):
            Documento.objects.create(
                tipo="recibido", direccion=direccion, contraparte="X",
                asunto=asunto, fecha=datetime.date(2026, 9, 1),
            )

    def test_lista_solo_muestra_oficios_de_su_direccion(self):
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("seguimientos_oficios:documento_list"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Oficio propio")
        self.assertNotContains(respuesta, "Oficio ajeno")

    def test_alta_solo_en_direccion_visible(self):
        self.client.force_login(self.user)
        datos = {
            "tipo": "enviado", "contraparte": "Cabildo", "asunto": "Nuevo",
            "fecha": "2026-09-02", "direccion": str(self.dir_ajena.pk),
        }
        respuesta = self.client.post(reverse("seguimientos_oficios:documento_create"), datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Documento.objects.filter(asunto="Nuevo").exists())
        datos["direccion"] = str(self.dir_propia.pk)
        self.client.post(reverse("seguimientos_oficios:documento_create"), datos)
        self.assertTrue(Documento.objects.filter(asunto="Nuevo", creado_por=self.user).exists())

    def test_sin_membresia_no_accede(self):
        otro = get_user_model().objects.create_user(email="sin@example.test")
        self.client.force_login(otro)
        respuesta = self.client.get(reverse("seguimientos_oficios:documento_list"))
        self.assertIn(respuesta.status_code, (302, 403))
