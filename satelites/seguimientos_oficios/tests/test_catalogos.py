from django.urls import reverse

from apps.security.models import Dependencia, UserAppRole
from satelites.seguimientos_oficios.models import Direccion, Nomenclatura
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P

from .base import BaseAdjuntos


class CatalogosTests(BaseAdjuntos):
    def como_owner(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.force_login(self.user)

    def test_solo_quien_tiene_permiso_administra_catalogos(self):
        self.client.force_login(self.user)
        for nombre, args in (("catalogos", []), ("direccion_crear", []), ("direccion_editar", [self.direccion.pk])):
            self.assertIn(self.client.get(reverse(f"seguimientos_oficios:{nombre}", args=args)).status_code, (302, 403))
        respuesta = self.client.post(reverse("seguimientos_oficios:direccion_crear"), {"nombre": "Intruso"})
        self.assertIn(respuesta.status_code, (302, 403))
        self.assertFalse(Direccion.objects.filter(nombre="Intruso").exists())

    def test_el_menu_muestra_catalogos_solo_a_quien_puede_administrarlos(self):
        lista = reverse("seguimientos_oficios:documento_list")
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(lista), reverse("seguimientos_oficios:catalogos"))
        self.como_owner()
        respuesta = self.client.get(lista)
        self.assertContains(respuesta, reverse("seguimientos_oficios:catalogos"))
        self.assertContains(respuesta, reverse("seguimientos_oficios:configuracion"))

    def test_crear_direccion_vinculada_a_dependencia(self):
        self.como_owner()
        egresos = Dependencia.objects.create(nombre="Egresos")
        respuesta = self.client.post(
            reverse("seguimientos_oficios:direccion_crear"),
            {"nombre": "Egresos y Finanzas", "dependencia": str(egresos.pk), "is_active": "on"},
        )
        nueva = Direccion.objects.get(nombre="Egresos y Finanzas")
        self.assertRedirects(respuesta, reverse("seguimientos_oficios:direccion_editar", args=[nueva.pk]))
        self.assertEqual((nueva.dependencia_uuid, nueva.slug), (egresos.pk, "egresos-y-finanzas"))
        self.assertContains(self.client.get(reverse("seguimientos_oficios:catalogos")), "Egresos y Finanzas")

    def test_dependencia_inexistente_o_nombre_repetido_se_rechazan(self):
        self.como_owner()
        url = reverse("seguimientos_oficios:direccion_crear")
        self.client.post(url, {"nombre": "X", "dependencia": "11111111-1111-1111-1111-111111111111"})
        self.assertFalse(Direccion.objects.filter(nombre="X").exists())
        self.client.post(url, {"nombre": self.direccion.nombre})
        self.assertEqual(Direccion.objects.filter(nombre=self.direccion.nombre).count(), 1)

    def test_editar_no_cambia_la_carpeta(self):
        self.como_owner()
        self.client.post(
            reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk]),
            {"nombre": "Innovación y Gobierno Digital", "dependencia": str(self.dep.pk), "is_active": "on"},
        )
        self.direccion.refresh_from_db()
        self.assertEqual((self.direccion.nombre, self.direccion.slug), ("Innovación y Gobierno Digital", "innovacion"))

    def test_nomenclaturas_crear_validar_editar_y_desactivar(self):
        self.como_owner()
        crear = reverse("seguimientos_oficios:nomenclatura_crear", args=[self.direccion.pk])
        self.client.post(crear, {"clase": "vale_prestamo", "plantilla": "VP-{n:03d}/{anio}"})
        vale = Nomenclatura.objects.get(direccion=self.direccion, clase="vale_prestamo")
        self.assertEqual(vale.ejemplo[:3], "VP-")
        self.client.post(crear, {"clase": "vale_prestamo", "plantilla": "OTRA-{n}"})
        self.client.post(crear, {"clase": "comunicado", "plantilla": "SIN-NUMERO"})
        self.assertEqual(self.direccion.nomenclaturas.count(), 2)
        actualizar = reverse("seguimientos_oficios:nomenclatura_actualizar", args=[vale.pk])
        self.client.post(actualizar, {"plantilla": "{n.__class__}"})
        vale.refresh_from_db()
        self.assertEqual(vale.plantilla, "VP-{n:03d}/{anio}")
        self.client.post(actualizar, {"plantilla": "VPR-{n:04d}/{anio}"})
        vale.refresh_from_db()
        self.assertEqual(vale.plantilla, "VPR-{n:04d}/{anio}")
        self.client.post(actualizar, {"accion": "estado"})
        vale.refresh_from_db()
        self.assertFalse(vale.is_active)

    def test_nomenclatura_desactivada_bloquea_enviados_nuevos(self):
        from django.core.exceptions import ValidationError
        import datetime
        from satelites.seguimientos_oficios.services import crear_documento

        Nomenclatura.objects.filter(direccion=self.direccion, clase="oficio").update(is_active=False)
        with self.assertRaises(ValidationError):
            crear_documento(
                usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
                contraparte="X", asunto="Y", fecha=datetime.date(2026, 9, 1),
            )
