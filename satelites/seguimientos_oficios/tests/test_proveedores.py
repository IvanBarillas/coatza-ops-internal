"""Contrato de la capacidad `prestamos.vales` que este satélite ofrece a otros (docs/contratos-satelites.md)."""
import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model

from apps.shared.module_sdk.integrations import integration_registry
from satelites.seguimientos_oficios.prestamos.services import registrar_devolucion

from .test_prestamos import PrestamosBase


class ProveedorValesTests(PrestamosBase):
    def peticion(self, usuario=None, root=False):
        return SimpleNamespace(user=usuario or self.user, axentra_is_root=root)

    def test_esta_registrado_por_nombre(self):
        proveedor = integration_registry.resolve("prestamos.vales")
        self.assertTrue(proveedor.available)

    def test_resolver_devuelve_la_ficha_con_estado_y_url(self):
        documento, _ = self.vale([self.starlink, self.laptop])
        ficha = integration_registry.resolve("prestamos.vales").resolver(self.peticion(), documento.pk)
        self.assertEqual(set(ficha), {"tipo", "id", "etiqueta", "detalle", "estado", "url"})
        self.assertEqual((ficha["tipo"], ficha["id"]), ("prestamos.vale", str(documento.pk)))
        self.assertIn(ficha["estado"], ("vigente", "por_vencer", "vencido"))
        self.assertIn("VP-IN-001/2026", ficha["etiqueta"])
        self.assertIn("Starlink", ficha["detalle"])
        self.assertTrue(ficha["url"].endswith(f"/{documento.pk}/imprimir/"))

    def test_resolver_no_lanza_con_ids_raros_ni_muestra_lo_que_no_se_puede_ver(self):
        documento, _ = self.vale()
        proveedor = integration_registry.resolve("prestamos.vales")
        self.assertIsNone(proveedor.resolver(self.peticion(), uuid.uuid4()))
        self.assertIsNone(proveedor.resolver(self.peticion(), "no-es-uuid"))
        ajeno = get_user_model().objects.create_user(email="ajeno@example.test")
        self.assertIsNone(proveedor.resolver(self.peticion(ajeno), documento.pk))       # sin membresía ni alcance
        self.assertIsNotNone(proveedor.resolver(self.peticion(root=True), documento.pk))

    def test_buscar_filtra_por_texto_y_solo_ofrece_abiertos(self):
        abierto, _ = self.vale([self.starlink])
        devuelto, prestamo = self.vale([self.laptop])
        proveedor = integration_registry.resolve("prestamos.vales")
        self.assertEqual({f["id"] for f in proveedor.buscar(self.peticion(), "")}, {str(abierto.pk), str(devuelto.pk)})
        registrar_devolucion(prestamo, usuario=self.user)
        self.assertEqual([f["id"] for f in proveedor.buscar(self.peticion(), "")], [str(abierto.pk)])
        self.assertEqual({f["id"] for f in proveedor.buscar(self.peticion(), "", solo_abiertos=False)}, {str(abierto.pk), str(devuelto.pk)})
        self.assertEqual([f["id"] for f in proveedor.buscar(self.peticion(), "001/2026", solo_abiertos=False)], [str(abierto.pk)])
        self.assertEqual(len(proveedor.buscar(self.peticion(), "", limite=1, solo_abiertos=False)), 1)
        self.assertEqual(proveedor.buscar(self.peticion(), "zzz"), [])
