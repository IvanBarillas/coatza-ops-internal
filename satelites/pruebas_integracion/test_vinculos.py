"""De extremo a extremo: lo que Eventos usa de Oficios y Telefonía aparece como «Relacionado» en el detalle de cada uno."""
import datetime
from unittest import skipUnless

from django.apps import apps
from django.urls import reverse

from satelites.eventos.tests.base import BaseEventos

TRES = all(apps.is_installed(a) for a in ("satelites.eventos", "satelites.seguimientos_oficios", "satelites.telefonia"))


@skipUnless(TRES, "requiere Eventos, Oficios y Telefonía instalados")
class VinculosRealesTests(BaseEventos):
    def test_la_linea_y_el_vale_muestran_el_evento_relacionado_y_la_linea_se_elige_de_la_lista(self):
        from apps.security.models import AppModule, UserAppRole
        from satelites.seguimientos_oficios.models import Bien, Direccion, Nomenclatura
        from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as PO
        from satelites.seguimientos_oficios.prestamos.services import crear_vale
        from satelites.telefonia.models import Linea
        from satelites.telefonia.permissions import TelefoniaPermissions as PT

        dep = self.area.dependencia
        for slug, permisos, rol in ((PO.APP_CODE, PO, "prestamos"), (PT.APP_CODE, PT, "operador")):
            modulo, _ = AppModule.objects.get_or_create(slug=slug, defaults={"name": slug})
            modulo.is_active = True
            modulo.save()
            UserAppRole.objects.create(user=self.coord, app=modulo, role=rol, permissions_list=permisos.ROLE_MAPPING[rol])
        direccion = Direccion.objects.create(nombre="Innovación", dependencia_uuid=dep.pk, folio_manual=False, vales_habilitados=True)
        Nomenclatura.objects.create(direccion=direccion, clase="vale_prestamo", plantilla="VP-{n:03d}/{anio}")
        bien = Bien.objects.create(direccion=direccion, nombre="Bocina", identificador="B-1")
        hoy = datetime.date.today()
        documento, _ = crear_vale(
            usuario=self.coord, direccion=direccion, bienes=[bien], fecha_entrega=hoy, fecha_limite=hoy + datetime.timedelta(days=3),
            contraparte="Innovación", contraparte_dependencia_uuid=dep.pk,
        )
        linea = Linea.objects.create(identificador="9212165053", sitio="Biblioteca")
        e = self.evento("Feria del libro")
        self.client.force_login(self.coord)
        detalle = reverse("eventos:evento_detalle", args=[e.pk])
        self.assertContains(self.client.get(detalle), "9212165053")                    # la línea se ofrece en la lista
        self.client.post(detalle, {"accion": "vale", "vale": str(documento.pk)})
        self.client.post(detalle, {"accion": "tramite", "tipo": "reubicacion", "descripcion": "Llevarla", "linea": str(linea.pk)})
        self.assertEqual(str(e.tramites.get().ref_id), str(linea.pk))

        pagina = self.client.get(reverse("telefonia:linea_detalle", args=[linea.pk]))
        self.assertContains(pagina, "Relacionado (1)")
        self.assertContains(pagina, "Feria del libro")
        self.assertContains(pagina, "Trámite en el evento")
        pagina = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertContains(pagina, "Relacionado (1)")
        self.assertContains(pagina, "Salió al evento")
        self.assertContains(pagina, reverse("eventos:evento_detalle", args=[e.pk]))
