import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Gestor
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import crear_documento, editar_documento

from .base import BaseAdjuntos


class GestorObligatorioTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.legado = Gestor.objects.create(direccion=self.direccion, nombre="Sin cuenta")
        self.client.force_login(self.user)

    def enviar(self, gestor):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="X", asunto="A", fecha=datetime.date(2026, 9, 1), gestor=gestor,
        )

    def como_owner(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])

    def test_no_se_asigna_un_gestor_sin_usuario(self):
        with self.assertRaises(ValidationError):
            self.enviar(self.legado)
        self.enviar(self.gestor("Con cuenta"))

    def test_el_formulario_solo_ofrece_gestores_con_usuario(self):
        con_cuenta = self.gestor("Con cuenta")
        gestores = self.client.get(reverse("seguimientos_oficios:documento_create")).context["form"].fields["gestor"].queryset
        self.assertEqual(list(gestores), [con_cuenta])

    def test_un_gestor_heredado_ya_asignado_no_bloquea_editar_otros_datos(self):
        documento = self.enviar(None)
        Gestor.objects.filter(pk=self.legado.pk).update(is_active=True)
        type(documento).objects.filter(pk=documento.pk).update(gestor=self.legado)
        documento.refresh_from_db()
        editar_documento(documento, usuario=self.user, cambios={"asunto": "Nuevo asunto"})
        documento.refresh_from_db()
        self.assertEqual((documento.asunto, documento.gestor_id), ("Nuevo asunto", self.legado.pk))
        pantalla = self.client.get(reverse("seguimientos_oficios:documento_editar", args=[documento.pk]))
        self.assertIn(self.legado, pantalla.context["form"].fields["gestor"].queryset)
        with self.assertRaises(ValidationError):
            editar_documento(self.enviar(None), usuario=self.user, cambios={"gestor": self.legado})

    def test_el_catalogo_agrega_por_usuario_y_el_nombre_sale_de_la_cuenta(self):
        self.como_owner()
        usuario = get_user_model().objects.create_user(email="ana@example.test", first_name="Ana", last_name="López")
        UserAppRole.objects.create(user=usuario, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        crear = reverse("seguimientos_oficios:gestor_crear", args=[self.direccion.pk])
        self.client.post(crear, {"usuario": ""})
        self.assertFalse(Gestor.objects.filter(nombre="Ana López").exists())
        self.client.post(crear, {"usuario": str(usuario.pk)})
        gestor = Gestor.objects.get(usuario=usuario)
        self.assertEqual(gestor.nombre, "Ana López")
        self.client.post(crear, {"usuario": str(usuario.pk)})
        self.assertEqual(Gestor.objects.filter(usuario=usuario).count(), 1)

    def test_dos_personas_con_el_mismo_nombre_se_distinguen_por_correo(self):
        self.como_owner()
        crear = reverse("seguimientos_oficios:gestor_crear", args=[self.direccion.pk])
        for correo in ("uno@example.test", "dos@example.test"):
            usuario = get_user_model().objects.create_user(email=correo, first_name="Luis", last_name="Pérez")
            UserAppRole.objects.create(user=usuario, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
            self.client.post(crear, {"usuario": str(usuario.pk)})
        self.assertEqual(
            sorted(Gestor.objects.filter(nombre__startswith="Luis").values_list("nombre", flat=True)),
            ["Luis Pérez", "Luis Pérez (dos@example.test)"],
        )

    def test_el_catalogo_marca_al_gestor_sin_usuario(self):
        self.como_owner()
        pagina = self.client.get(reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk]))
        self.assertContains(pagina, "Sin usuario: no se puede asignar")
        self.assertContains(pagina, "Agregar gestor")
