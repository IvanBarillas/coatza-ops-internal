import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import cancelar_documento, editar_documento

from .base import BaseAdjuntos


class EdicionTests(BaseAdjuntos):
    def test_edicion_deja_valor_anterior_y_nuevo(self):
        documento = self.documento()
        editar_documento(
            documento, usuario=self.user, motivo="Error en el número de serie del equipo X",
            cambios={"asunto": "Alta del equipo serie 123", "contraparte": "Tesorería"},
        )
        documento.refresh_from_db()
        self.assertEqual(documento.asunto, "Alta del equipo serie 123")
        entrada = documento.historial.last()
        self.assertEqual(entrada.accion, "editado")
        self.assertEqual(entrada.datos["cambios"], {"asunto": {"antes": "Asunto", "despues": "Alta del equipo serie 123"}})
        self.assertEqual(entrada.datos["motivo"], "Error en el número de serie del equipo X")

    def test_sin_cambios_se_rechaza(self):
        documento = self.documento()
        with self.assertRaises(ValidationError):
            editar_documento(documento, usuario=self.user, cambios={"asunto": "  Asunto "})

    def test_campos_congelados_no_se_editan(self):
        documento = self.documento()
        for campo in ("folio", "director_nombre", "clase", "sentido", "direccion"):
            with self.assertRaises(ValidationError):
                editar_documento(documento, usuario=self.user, cambios={campo: "otro"})

    def test_folio_del_remitente_si_se_corrige_en_recibidos(self):
        documento = self.documento("recibido")
        editar_documento(documento, usuario=self.user, cambios={"folio": "TES/45/2026"})
        documento.refresh_from_db()
        self.assertEqual(documento.folio, "TES/45/2026")
        self.assertEqual(documento.historial.last().datos["cambios"]["folio"]["despues"], "TES/45/2026")

    def test_fecha_de_enviado_debe_conservar_el_anio_del_folio(self):
        documento = self.documento()
        editar_documento(documento, usuario=self.user, cambios={"fecha": datetime.date(2026, 12, 31)})
        with self.assertRaises(ValidationError):
            editar_documento(documento, usuario=self.user, cambios={"fecha": datetime.date(2027, 1, 2)})

    def test_cancelado_no_se_edita_pero_concluido_si(self):
        documento = self.documento()
        cancelar_documento(documento, usuario=self.user, motivo="Registrado por error en la captura")
        with self.assertRaises(ValidationError):
            editar_documento(documento, usuario=self.user, cambios={"asunto": "Nuevo"})
        otro = self.entregado()
        type(otro).objects.filter(pk=otro.pk).update(estado="concluido")
        editar_documento(otro, usuario=self.user, cambios={"asunto": "Corregido tras concluir"})
        self.assertEqual(type(otro).objects.get(pk=otro.pk).asunto, "Corregido tras concluir")

    def test_vista_edita_y_muestra_el_cambio_en_el_historial(self):
        documento = self.documento()
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:documento_editar", args=[documento.pk])
        self.assertContains(self.client.get(url), "Editar")
        respuesta = self.client.post(url, {
            "contraparte": "Contraloría", "asunto": "Asunto corregido", "fecha": "2026-09-01",
            "motivo": "Typo",
        })
        self.assertRedirects(respuesta, reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertContains(detalle, "Asunto → Asunto corregido")
        self.assertContains(detalle, "Contraloría")

    def test_viewer_no_puede_editar(self):
        UserAppRole.objects.filter(user=self.user).update(role="viewer", permissions_list=P.ROLE_MAPPING["viewer"])
        documento = self.documento()
        self.client.force_login(self.user)
        url = reverse("seguimientos_oficios:documento_editar", args=[documento.pk])
        self.assertIn(self.client.get(url).status_code, (302, 403))
        self.client.post(url, {"contraparte": "X", "asunto": "Hackeado", "fecha": "2026-09-01"})
        documento.refresh_from_db()
        self.assertEqual(documento.asunto, "Asunto")
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])), "/editar/")
