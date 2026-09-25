from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Bien, CategoriaBien, Direccion
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P

from .test_prestamos import PrestamosBase


class CategoriasDeBienesTests(PrestamosBase):
    def setUp(self):
        super().setUp()
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.computo = CategoriaBien.objects.create(direccion=self.direccion, nombre="Cómputo")
        self.energia = CategoriaBien.objects.create(direccion=self.direccion, nombre="Energía eléctrica")

    def test_catalogo_crea_renombra_y_desactiva_y_vuelve_a_su_seccion(self):
        r = self.client.post(reverse("seguimientos_oficios:categoria_bien_crear", args=[self.direccion.pk]), {"nombre": "  Audio  y video "})
        self.assertTrue(r["Location"].endswith("?seccion=bienes"))
        audio = CategoriaBien.objects.get(nombre="Audio y video")
        self.client.post(reverse("seguimientos_oficios:categoria_bien_actualizar", args=[audio.pk]), {"nombre": "Audio"})
        self.client.post(reverse("seguimientos_oficios:categoria_bien_actualizar", args=[audio.pk]), {"accion": "estado"})
        audio.refresh_from_db()
        self.assertEqual((audio.nombre, audio.is_active), ("Audio", False))

    def test_no_repite_nombre_en_la_direccion_ni_sin_importar_mayusculas(self):
        self.client.post(reverse("seguimientos_oficios:categoria_bien_crear", args=[self.direccion.pk]), {"nombre": "cómputo"})
        self.assertEqual(CategoriaBien.objects.filter(direccion=self.direccion).count(), 2)

    def test_el_bien_guarda_su_categoria_y_la_bitacora_registra_el_cambio(self):
        url = reverse("seguimientos_oficios:bien_editar", args=[self.laptop.pk])
        self.client.post(url, {
            "direccion": self.direccion.pk, "nombre": "Laptop", "categoria": self.computo.pk, "marca_modelo": "", "identificador": "LT-77",
            "folio_inventario": "", "descripcion": "", "estado": "disponible", "motivo": "",
        })
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.categoria, self.computo)
        entrada = self.laptop.historial.filter(accion="editado").get()
        self.assertEqual(entrada.datos["cambios"]["categoria"], {"antes": "", "despues": "Cómputo"})

    def test_no_acepta_categoria_de_otra_direccion(self):
        otra = Direccion.objects.create(nombre="Egresos", folio_manual=False, vales_habilitados=True)
        ajena = CategoriaBien.objects.create(direccion=otra, nombre="Ajena")
        r = self.client.post(reverse("seguimientos_oficios:bien_editar", args=[self.laptop.pk]), {
            "direccion": self.direccion.pk, "nombre": "Laptop", "categoria": ajena.pk, "identificador": "LT-77", "estado": "disponible",
        })
        self.assertEqual(r.status_code, 200)
        self.laptop.refresh_from_db()
        self.assertIsNone(self.laptop.categoria)

    def test_lista_de_bienes_filtra_por_categoria(self):
        Bien.objects.filter(pk=self.laptop.pk).update(categoria=self.computo)
        url = reverse("seguimientos_oficios:bienes")
        pagina = self.client.get(url, {"categoria": str(self.computo.pk)})
        self.assertEqual([b.nombre for b in pagina.context["pagina"]], ["Laptop"])
        sin = self.client.get(url, {"categoria": "sin"})
        self.assertEqual([b.nombre for b in sin.context["pagina"]], ["Starlink"])

    def test_el_formulario_del_vale_ofrece_los_bienes_con_su_categoria(self):
        Bien.objects.filter(pk=self.laptop.pk).update(categoria=self.computo)
        pagina = self.client.get(reverse("seguimientos_oficios:vale_crear"))
        datos = {b["texto"].split(" · ")[0]: b["categoria"] for b in pagina.context["bienes_data"]}
        self.assertEqual(datos, {"Laptop": str(self.computo.pk), "Starlink": ""})
        self.assertEqual([c["nombre"] for c in pagina.context["categorias_data"]], ["Cómputo", "Energía eléctrica"])
        self.assertContains(pagina, 'name="bienes"')
