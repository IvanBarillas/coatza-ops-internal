import datetime
import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Documento, Gestor
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import _leer_pdf, crear_documento

from .base import PDF, BaseAdjuntos, pdf


def foto(formato="JPEG", tamano=(600, 400), orientacion=None, nombre="acuse.jpg"):
    imagen = Image.new("RGB", tamano, (200, 30, 30))
    salida = io.BytesIO()
    if formato == "JPEG" and orientacion:
        exif = Image.Exif()
        exif[0x0112] = orientacion
        imagen.save(salida, "JPEG", exif=exif)
    else:
        imagen.save(salida, formato)
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type="image/" + formato.lower())


class FotosTests(BaseAdjuntos):
    def test_una_foto_jpg_o_png_se_convierte_en_pdf(self):
        for formato, nombre in (("JPEG", "acuse.jpg"), ("PNG", "acuse.png")):
            contenido, nombre_pdf = _leer_pdf(foto(formato, nombre=nombre))
            self.assertTrue(contenido.startswith(b"%PDF-"))
            self.assertEqual(nombre_pdf, "acuse.pdf")

    def test_un_pdf_pasa_igual_y_lo_demas_se_rechaza(self):
        contenido, nombre = _leer_pdf(pdf("a.pdf"))
        self.assertEqual((contenido, nombre), (PDF, "a.pdf"))
        for malo in (SimpleUploadedFile("x.txt", b"hola"), SimpleUploadedFile("x.jpg", b"\xff\xd8\xffroto")):
            with self.assertRaises(ValidationError):
                _leer_pdf(malo)

    def test_la_orientacion_de_la_camara_se_respeta(self):
        contenido, _ = _leer_pdf(foto("JPEG", tamano=(600, 400), orientacion=6))
        self.assertIn(b"/Width 400", contenido)
        self.assertIn(b"/Height 600", contenido)

    def test_las_fotos_enormes_se_reducen(self):
        contenido, _ = _leer_pdf(foto("PNG", tamano=(6000, 4000)))
        self.assertIn(b"/Width 3508", contenido)

    def test_la_subida_normal_tambien_acepta_fotos(self):
        from satelites.seguimientos_oficios.services import adjuntar_pdf

        documento = self.documento("recibido")
        adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=foto())
        self.assertEqual((adjunto.rol, adjunto.nombre_original), ("original", "acuse.pdf"))
        self.assertEqual(adjunto.ocr.estado, "pendiente")


class GestorMovilTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_user(email="juan@example.test", first_name="Juan")
        UserAppRole.objects.create(user=self.usuario, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        self.juan = Gestor.objects.create(direccion=self.direccion, usuario=self.usuario)
        self.maria = self.gestor("María")

    def enviar(self, asunto, gestor):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="Tesorería", asunto=asunto, fecha=datetime.date(2026, 9, 1), gestor=gestor,
        )

    def entrar(self):
        self.client.force_login(self.usuario)

    def entrega(self, documento, **datos):
        return self.client.post(reverse("seguimientos_oficios:gestor_entrega", args=[documento.pk]), datos)

    def test_ve_solo_sus_pendientes_y_no_el_resto_del_modulo(self):
        propio, ajeno = self.enviar("Oficio de Juan", self.juan), self.enviar("Oficio de María", self.maria)
        self.entrar()
        pagina = self.client.get(reverse("seguimientos_oficios:gestor"))
        self.assertContains(pagina, "Oficio de Juan")
        self.assertNotContains(pagina, "Oficio de María")
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[propio.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[ajeno.pk])).status_code, 404)
        for nombre in ("documento_list", "busqueda", "seguimiento", "catalogos", "documento_create"):
            self.assertIn(self.client.get(reverse(f"seguimientos_oficios:{nombre}")).status_code, (302, 403), nombre)

    def test_el_menu_del_gestor_solo_tiene_mis_pendientes(self):
        self.entrar()
        pagina = self.client.get(reverse("seguimientos_oficios:gestor"))
        self.assertContains(pagina, reverse("seguimientos_oficios:gestor"))
        self.assertNotContains(pagina, reverse("seguimientos_oficios:documento_create"))
        self.assertNotContains(pagina, reverse("seguimientos_oficios:busqueda"))

    def test_la_entrada_del_modulo_lleva_a_cada_rol_a_su_vista(self):
        inicio = reverse("seguimientos_oficios:inicio")
        self.entrar()
        self.assertRedirects(self.client.get(inicio), reverse("seguimientos_oficios:gestor"), fetch_redirect_response=False)
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(inicio), reverse("seguimientos_oficios:documento_list"), fetch_redirect_response=False)
        seguimiento = get_user_model().objects.create_user(email="ve@example.test")
        UserAppRole.objects.create(user=seguimiento, app=self.app, role="seguimiento", permissions_list=P.ROLE_MAPPING["seguimiento"])
        self.client.force_login(seguimiento)
        self.assertRedirects(self.client.get(inicio), reverse("seguimientos_oficios:seguimiento"), fetch_redirect_response=False)

    def test_entrega_con_foto_del_acuse_concluye_el_oficio_desde_generado(self):
        documento = self.enviar("Todo en un paso", self.juan)
        self.entrar()
        respuesta = self.entrega(documento, fecha_entrega="2026-09-02", receptor="Recepción Tesorería", archivo=foto())
        self.assertRedirects(respuesta, reverse("seguimientos_oficios:gestor"), fetch_redirect_response=False)
        documento.refresh_from_db()
        self.assertEqual((documento.estado, documento.receptor_entrega), ("concluido", "Recepción Tesorería"))
        adjunto = documento.adjuntos.get()
        self.assertEqual((adjunto.rol, adjunto.nombre_original, adjunto.subido_por_id), ("evidencia", "acuse.pdf", self.usuario.pk))
        self.assertEqual(documento.historial.filter(accion="adjuntado").last().datos["origen"], "movil")
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:gestor")), "Todo en un paso")

    def test_entrega_sin_foto_deja_entregado_y_luego_sube_el_acuse(self):
        documento = self.enviar("En dos pasos", self.juan)
        self.entrar()
        self.entrega(documento, receptor="Recepción")
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "entregado")
        self.assertContains(self.client.get(reverse("seguimientos_oficios:gestor")), "falta el acuse")
        self.entrega(documento, receptor="", fecha_entrega="")
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "entregado")
        self.entrega(documento, archivo=pdf("acuse.pdf"))
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "concluido")

    def test_validaciones_de_la_entrega(self):
        documento = self.enviar("Validaciones", self.juan)
        self.entrar()
        self.entrega(documento, receptor="  ")
        self.entrega(documento, receptor="R", fecha_entrega=str(datetime.date.today() + datetime.timedelta(days=3)))
        self.entrega(documento, receptor="R", archivo=SimpleUploadedFile("x.txt", b"no es imagen"))
        documento.refresh_from_db()
        self.assertEqual((documento.estado, documento.adjuntos.count()), ("generado", 0))

    def test_no_puede_tocar_oficios_de_otro_gestor_ni_ya_concluidos(self):
        ajeno, concluido = self.enviar("De María", self.maria), self.enviar("Ya concluido", self.juan)
        Documento.objects.filter(pk=concluido.pk).update(estado="concluido")
        self.entrar()
        self.assertEqual(self.entrega(ajeno, receptor="R").status_code, 404)
        self.assertEqual(self.entrega(concluido, receptor="R").status_code, 404)
        ajeno.refresh_from_db()
        self.assertEqual(ajeno.estado, "generado")

    def test_sin_gestor_vinculado_ve_el_aviso(self):
        Gestor.objects.filter(pk=self.juan.pk).update(usuario=None)
        self.entrar()
        self.assertContains(self.client.get(reverse("seguimientos_oficios:gestor")), "no está vinculado a un gestor")

    def test_solo_con_el_permiso_de_entrega_hay_formulario(self):
        self.enviar("Solo lectura", self.juan)
        UserAppRole.objects.filter(user=self.usuario).update(permissions_list=["has_access_module", "can_view_own_pendings"])
        self.entrar()
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:gestor")), "Registrar entrega")

    def test_vincular_usuarios_desde_catalogos(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.force_login(self.user)
        sin_membresia = get_user_model().objects.create_user(email="fuera@example.test")
        legado = Gestor.objects.create(direccion=self.direccion, nombre="Legado")
        actualizar = reverse("seguimientos_oficios:gestor_actualizar", args=[legado.pk])
        for candidato in (sin_membresia, self.usuario, None):
            self.client.post(actualizar, {"usuario": str(candidato.pk) if candidato else ""})
            legado.refresh_from_db()
            self.assertIsNone(legado.usuario)
        otro = get_user_model().objects.create_user(email="maria@example.test", first_name="María", last_name="Ruiz")
        UserAppRole.objects.create(user=otro, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        self.client.post(actualizar, {"usuario": str(otro.pk)})
        legado.refresh_from_db()
        self.assertEqual((legado.usuario, legado.nombre), (otro, "María Ruiz"))
        self.assertContains(self.client.get(reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk])), "maria@example.test")
