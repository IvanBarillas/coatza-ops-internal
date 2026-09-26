"""Prueba de extremo a extremo entre satélites. Vive fuera de ambos para que ninguno importe al otro; se omite si falta alguno."""
import datetime

from django.apps import apps
from unittest import skipUnless
from django.urls import reverse

from satelites.eventos.tests.base import BaseEventos, momento

AMBOS = apps.is_installed("satelites.eventos") and apps.is_installed("satelites.seguimientos_oficios")


@skipUnless(AMBOS, "requiere Eventos y Seguimiento de oficios instalados")
class EventosConValesRealesTests(BaseEventos):
    def test_un_vale_real_se_elige_en_el_evento_y_se_abre(self):
        from apps.security.models import UserAppRole
        from satelites.seguimientos_oficios.models import Bien, Direccion, Nomenclatura
        from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as PO
        from satelites.seguimientos_oficios.prestamos.services import crear_vale

        dep = self.area.dependencia
        direccion = Direccion.objects.create(nombre="Innovación", dependencia_uuid=dep.pk, folio_manual=False, vales_habilitados=True)
        Nomenclatura.objects.create(direccion=direccion, clase="vale_prestamo", plantilla="VP-{n:03d}/{anio}")
        from apps.security.models import AppModule
        modulo, _ = AppModule.objects.get_or_create(slug=PO.APP_CODE, defaults={"name": "Oficios"})
        modulo.is_active = True
        modulo.save()
        UserAppRole.objects.create(user=self.coord, app=modulo, role="prestamos", permissions_list=PO.ROLE_MAPPING["prestamos"])
        bien = Bien.objects.create(direccion=direccion, nombre="Bocina", identificador="B-1")
        hoy = datetime.date.today()
        documento, _ = crear_vale(
            usuario=self.coord, direccion=direccion, bienes=[bien], fecha_entrega=hoy, fecha_limite=hoy + datetime.timedelta(days=3),
            contraparte="Innovación", contraparte_dependencia_uuid=dep.pk,
        )
        e = self.evento()
        self.client.force_login(self.coord)
        detalle = reverse("eventos:evento_detalle", args=[e.pk])
        self.assertContains(self.client.get(detalle), documento.folio)
        self.client.post(detalle, {"accion": "vale", "vale": str(documento.pk)})
        self.assertEqual(str(e.vales.get().ref_id), str(documento.pk))
        pagina = self.client.get(detalle)
        self.assertContains(pagina, reverse("seguimientos_oficios:vale_imprimir", args=[documento.pk]))
        self.assertContains(pagina, "Abrir vale")
