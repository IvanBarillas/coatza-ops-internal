import datetime

from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Categoria, Direccion, Documento
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import crear_documento, editar_documento

from .base import BaseAdjuntos
from django.core.exceptions import ValidationError


class CategoriasTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.panteones = Categoria.objects.create(direccion=self.direccion, nombre="Panteones")
        self.escuelas = Categoria.objects.create(direccion=self.direccion, nombre="Escuelas")
        self.client.force_login(self.user)

    def registrar(self, asunto, categoria=None, sentido="recibido"):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido=sentido, clase="oficio",
            contraparte="X", asunto=asunto, fecha=datetime.date(2026, 9, 1), categoria=categoria,
            folio="F-" + asunto if sentido == "enviado" else "",
        )

    def test_catalogo_crear_renombrar_desactivar_y_sin_duplicados(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        crear = reverse("seguimientos_oficios:categoria_crear", args=[self.direccion.pk])
        self.client.post(crear, {"nombre": "  Obras   Públicas "})
        self.assertTrue(Categoria.objects.filter(direccion=self.direccion, nombre="Obras Públicas").exists())
        self.client.post(crear, {"nombre": "panteones"})
        self.assertEqual(Categoria.objects.filter(direccion=self.direccion, nombre__iexact="panteones").count(), 1)
        actualizar = reverse("seguimientos_oficios:categoria_actualizar", args=[self.escuelas.pk])
        self.client.post(actualizar, {"nombre": "Escuelas y planteles"})
        self.escuelas.refresh_from_db()
        self.assertEqual(self.escuelas.nombre, "Escuelas y planteles")
        self.client.post(actualizar, {"accion": "estado"})
        self.escuelas.refresh_from_db()
        self.assertFalse(self.escuelas.is_active)
        pagina = self.client.get(reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk]))
        self.assertContains(pagina, 'id="categorias"')
        self.assertContains(pagina, 'href="#categorias"')

    def test_solo_quien_administra_catalogos_gestiona_categorias(self):
        self.client.post(reverse("seguimientos_oficios:categoria_crear", args=[self.direccion.pk]), {"nombre": "Intrusa"})
        self.assertFalse(Categoria.objects.filter(nombre="Intrusa").exists())

    def test_la_categoria_es_opcional_y_se_guarda_al_registrar(self):
        url = reverse("seguimientos_oficios:documento_create")
        datos = {
            "sentido": "recibido", "clase": "oficio", "direccion": str(self.direccion.pk), "fecha": "2026-09-02",
            "contraparte": "Ciudadano", "asunto": "Sin categoría", "folio": "R-1", "categoria": "",
        }
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertIsNone(Documento.objects.get(asunto="Sin categoría").categoria)
        self.client.post(url, {**datos, "asunto": "Con categoría", "categoria": str(self.panteones.pk)})
        self.assertEqual(Documento.objects.get(asunto="Con categoría").categoria, self.panteones)
        self.assertContains(self.client.get(url), "Sin categoría")

    def test_categoria_de_otra_direccion_o_inactiva_se_rechaza(self):
        otra = Direccion.objects.create(nombre="Egresos", folio_manual=False)
        ajena = Categoria.objects.create(direccion=otra, nombre="Ajena")
        with self.assertRaises(ValidationError):
            self.registrar("X", ajena)
        Categoria.objects.filter(pk=self.panteones.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.registrar("Y", Categoria.objects.get(pk=self.panteones.pk))
        url = reverse("seguimientos_oficios:documento_create")
        respuesta = self.client.post(url, {
            "sentido": "recibido", "clase": "oficio", "direccion": str(self.direccion.pk), "fecha": "2026-09-02",
            "contraparte": "X", "asunto": "Ajena", "folio": "R-9", "categoria": str(ajena.pk),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Documento.objects.filter(asunto="Ajena").exists())

    def test_lista_filtra_por_categoria_y_sin_categoria(self):
        self.registrar("Del panteón", self.panteones)
        self.registrar("De la escuela", self.escuelas)
        self.registrar("Sin tema")
        lista = lambda **kw: self.client.get(reverse("seguimientos_oficios:documento_list"), {"tab": "todos", **kw})
        self.assertContains(lista(categoria=str(self.panteones.pk)), "Del panteón")
        self.assertNotContains(lista(categoria=str(self.panteones.pk)), "De la escuela")
        solo_sin = lista(categoria="sin")
        self.assertContains(solo_sin, "Sin tema")
        self.assertNotContains(solo_sin, "Del panteón")
        self.assertContains(lista(), "Panteones")

    def test_la_busqueda_filtra_por_categoria_y_la_muestra(self):
        self.registrar("Requerimiento del panteón", self.panteones)
        self.registrar("Requerimiento de escuela", self.escuelas)
        respuesta = self.client.get(reverse("seguimientos_oficios:busqueda"), {"q": "requerimiento", "categoria": str(self.panteones.pk)})
        self.assertContains(respuesta, "Requerimiento del panteón")
        self.assertNotContains(respuesta, "Requerimiento de escuela")
        self.assertContains(respuesta, "· Panteones ·")
        self.assertTrue(respuesta.context["filtros_activos"])

    def test_editar_cambia_la_categoria_con_historial_y_conserva_la_inactiva(self):
        documento = self.registrar("Cambiante", self.panteones)
        editar_documento(documento, usuario=self.user, cambios={"categoria": self.escuelas})
        documento.refresh_from_db()
        self.assertEqual(documento.categoria, self.escuelas)
        self.assertEqual(documento.historial.last().datos["cambios"]["categoria"], {"antes": "Panteones", "despues": "Escuelas"})
        editar_documento(documento, usuario=self.user, cambios={"categoria": None})
        documento.refresh_from_db()
        self.assertIsNone(documento.categoria)
        self.assertEqual(documento.historial.first().datos["categoria"], "Panteones")
        Categoria.objects.filter(pk=self.escuelas.pk).update(is_active=False)
        con_inactiva = self.registrar("Ya clasificado", Categoria.objects.get(pk=self.panteones.pk))
        Categoria.objects.filter(pk=self.panteones.pk).update(is_active=False)
        con_inactiva.refresh_from_db()
        editar_documento(con_inactiva, usuario=self.user, cambios={"asunto": "Sigue con su categoría inactiva"})
        con_inactiva.refresh_from_db()
        self.assertEqual(con_inactiva.categoria_id, self.panteones.pk)

    def test_la_pantalla_de_edicion_ofrece_categorias_y_el_detalle_la_muestra(self):
        documento = self.registrar("Para editar", self.panteones)
        url = reverse("seguimientos_oficios:documento_editar", args=[documento.pk])
        self.assertContains(self.client.get(url), 'name="categoria"')
        self.client.post(url, {
            "contraparte_dependencia": "", "contraparte": "X", "asunto": "Para editar", "fecha": "2026-09-01",
            "folio": "", "categoria": str(self.escuelas.pk),
        })
        documento.refresh_from_db()
        self.assertEqual(documento.categoria, self.escuelas)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])), "Escuelas")

    def test_la_lista_es_compacta_sin_columnas_de_categoria_ni_dias(self):
        self.registrar("Del panteón", self.panteones)
        pagina = self.client.get(reverse("seguimientos_oficios:documento_list"), {"tab": "todos"})
        contenido = pagina.content.decode()
        cabecera = contenido[contenido.index("<thead"):contenido.index("</thead>")]
        for columna in ("Fecha", "Folio", "Asunto", "Gestor", "Estado"):
            self.assertIn(columna, cabecera)
        for sobra in ("Categoría", "Días", "Clase", "Sentido", "Tipo", "Dirección"):
            self.assertNotIn(sobra, cabecera)
        self.assertContains(pagina, "De: X")
        self.assertContains(pagina, "Oficio · Recibido")
        # área con scroll propio y encabezado fijo para que "Todos" no sea una lista interminable
        self.assertContains(pagina, "max-h-[62vh] overflow-auto")
        self.assertContains(pagina, "sticky top-0")
        # la categoría sigue disponible como filtro y en el detalle, no como columna
        self.assertContains(pagina, "Todas las categorías")
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[Documento.objects.get(asunto="Del panteón").pk]))
        self.assertContains(detalle, "Panteones")
