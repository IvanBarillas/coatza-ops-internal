import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import (
    AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile,
)
from satelites.seguimientos_oficios.models import Direccion, Documento, Nomenclatura
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
        Nomenclatura.objects.create(direccion=cls.dir_propia, clase="vale_prestamo", plantilla="IN-{n:03d}/{anio}")
        for direccion, asunto in ((cls.dir_propia, "Oficio propio"), (cls.dir_ajena, "Oficio ajeno")):
            Documento.objects.create(
                sentido="recibido", estado="registrado", direccion=direccion, direccion_nombre=direccion.nombre, contraparte="X",
                asunto=asunto, fecha=datetime.date(2026, 9, 1),
            )

    def test_lista_solo_muestra_oficios_de_su_direccion(self):
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("seguimientos_oficios:documento_list"), {"tab": "todos"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Oficio propio")
        self.assertNotContains(respuesta, "Oficio ajeno")
        self.assertContains(respuesta, 'id="module-sidebar"')
        self.assertContains(respuesta, "data-menu-movil")
        self.assertContains(respuesta, "Registrar documento")

    def test_alta_solo_en_direccion_visible(self):
        self.client.force_login(self.user)
        datos = {
            "sentido": "enviado", "clase": "vale_prestamo", "contraparte": "Cabildo", "asunto": "Nuevo",
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

    def _documento(self, direccion, **extra):
        return Documento.objects.get(direccion=direccion, **extra)

    def test_detalle_solo_de_direccion_visible(self):
        self.client.force_login(self.user)
        propio = self._documento(self.dir_propia)
        ajeno = self._documento(self.dir_ajena)
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[propio.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[ajeno.pk])).status_code, 404)
        for accion in ("entregar", "cancelar"):
            respuesta = self.client.post(reverse(f"seguimientos_oficios:documento_{accion}", args=[ajeno.pk]), {})
            self.assertEqual(respuesta.status_code, 404)

    def test_editor_cancela_con_motivo_pero_no_un_concluido(self):
        self.client.force_login(self.user)
        url = lambda pk: reverse("seguimientos_oficios:documento_cancelar", args=[pk])
        documento = self._documento(self.dir_propia)
        self.client.post(url(documento.pk), {"motivo": "corto"})
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "registrado")
        self.client.post(url(documento.pk), {"motivo": "Registrado por error en la captura"})
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "cancelado")
        Documento.objects.filter(pk=documento.pk).update(estado="concluido", motivo_cancelacion="")
        self.client.post(url(documento.pk), {"motivo": "Registrado por error en la captura"})
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "concluido")

    def test_viewer_no_puede_cancelar_ni_entregar(self):
        UserAppRole.objects.filter(user=self.user).update(role="viewer", permissions_list=P.ROLE_MAPPING["viewer"])
        self.client.force_login(self.user)
        documento = self._documento(self.dir_propia)
        for accion, datos in (("cancelar", {"motivo": "Registrado por error en la captura"}),
                              ("entregar", {"fecha_entrega": "2026-09-02", "receptor": "X"})):
            respuesta = self.client.post(reverse(f"seguimientos_oficios:documento_{accion}", args=[documento.pk]), datos)
            self.assertIn(respuesta.status_code, (302, 403))
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "registrado")

    def test_menu_movil_marca_la_seccion_actual_y_llega_por_htmx(self):
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:documento_create")
        respuesta = self.client.get(url, headers={"HX-Request": "true", "HX-Target": "page-content"})
        contenido = respuesta.content.decode()
        self.assertIn("data-menu-movil", contenido)
        self.assertNotIn('id="module-sidebar"', contenido)
        self.assertRegex(contenido, r'aria-current="page"[^>]*>\s*<i[^>]*></i><span[^>]*>Registrar documento')
