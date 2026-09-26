"""Contrato de la capacidad `telefonia.lineas` que este satélite ofrece a otros (docs/contratos-satelites.md)."""
import uuid
from types import SimpleNamespace

from apps.shared.module_sdk.integrations import integration_registry

from satelites.telefonia.models import Linea

from .base import BaseTelefonia


class ProveedorLineasTests(BaseTelefonia):
    def peticion(self, con_permiso=True, root=False):
        """El proveedor consulta los permisos del usuario en Telefonía, no la lista del módulo que atiende la petición."""
        return SimpleNamespace(user=self.operador if con_permiso else self.ajeno, axentra_is_root=root, axentra_permissions_list=[])

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        self.ajeno = get_user_model().objects.create_user(email="ajeno@example.test")
        self.inactiva = Linea.objects.create(identificador="9211111111", sitio="Bodega", is_active=False)

    def test_esta_registrado_por_nombre(self):
        self.assertTrue(integration_registry.resolve("telefonia.lineas").available)

    def test_resolver_devuelve_la_ficha(self):
        ficha = integration_registry.resolve("telefonia.lineas").resolver(self.peticion(), self.linea.pk)
        self.assertEqual(set(ficha), {"tipo", "id", "etiqueta", "detalle", "estado", "url"})
        self.assertEqual((ficha["tipo"], ficha["id"], ficha["estado"]), ("telefonia.linea", str(self.linea.pk), "activa"))
        self.assertIn("9212165053", ficha["etiqueta"])
        self.assertTrue(ficha["url"].endswith(f"/lineas/{self.linea.pk}/"))

    def test_resolver_no_lanza_ni_muestra_a_quien_no_tiene_permiso(self):
        proveedor = integration_registry.resolve("telefonia.lineas")
        self.assertIsNone(proveedor.resolver(self.peticion(), uuid.uuid4()))
        self.assertIsNone(proveedor.resolver(self.peticion(), "no-es-uuid"))
        self.assertIsNone(proveedor.resolver(self.peticion(con_permiso=False), self.linea.pk))
        self.assertIsNotNone(proveedor.resolver(self.peticion(con_permiso=False, root=True), self.linea.pk))

    def test_buscar_filtra_por_texto_y_ofrece_solo_activas(self):
        proveedor = integration_registry.resolve("telefonia.lineas")
        self.assertEqual([f["id"] for f in proveedor.buscar(self.peticion(), "")], [str(self.linea.pk)])
        self.assertEqual({f["id"] for f in proveedor.buscar(self.peticion(), "", solo_activas=False)}, {str(self.linea.pk), str(self.inactiva.pk)})
        self.assertEqual([f["id"] for f in proveedor.buscar(self.peticion(), "allende")], [str(self.linea.pk)])
        self.assertEqual(proveedor.buscar(self.peticion(), "zzz"), [])
        self.assertEqual(proveedor.buscar(self.peticion(con_permiso=False), ""), [])
