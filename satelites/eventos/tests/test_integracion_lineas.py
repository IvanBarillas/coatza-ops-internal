"""Eventos consume `telefonia.lineas` por nombre y ofrece `vinculos.eventos`: con proveedor, sin él y con uno que ya no ve la línea."""
import uuid
from types import SimpleNamespace

from django.urls import reverse

from apps.shared.module_sdk.integrations import integration_registry
from satelites.eventos import services as svc
from satelites.eventos.proveedores import ProveedorVinculos

from .base import BaseEventos
from .test_integracion_vales import ProveedorFalso, ficha

NOMBRE = "telefonia.lineas"


class IntegracionLineasTests(BaseEventos):
    def proveedor(self, proveedor):
        antes = integration_registry._providers.get(NOMBRE)
        self.addCleanup(lambda: integration_registry._providers.__setitem__(NOMBRE, antes) if antes is not None else integration_registry._providers.pop(NOMBRE, None))
        if proveedor is None:
            integration_registry._providers.pop(NOMBRE, None)
        else:
            integration_registry.register(NOMBRE, proveedor, replace=True)

    def detalle(self, e):
        return reverse("eventos:evento_detalle", args=[e.pk])

    def linea(self, etiqueta="922-1 · Biblioteca"):
        f = ficha(etiqueta, "activa")
        f["tipo"], f["url"] = "telefonia.linea", f"/linea/{f['id']}/"
        return f

    def test_con_proveedor_se_elige_la_linea_y_se_guarda_uuid_y_etiqueta(self):
        f = self.linea()
        self.proveedor(ProveedorFalso([f]))
        e = self.evento()
        self.client.force_login(self.coord)
        self.assertContains(self.client.get(self.detalle(e)), "Línea del sistema")
        self.client.post(self.detalle(e), {"accion": "tramite", "tipo": "reubicacion", "descripcion": "Llevarla al malecón", "linea": f["id"]})
        t = e.tramites.get()
        self.assertEqual((str(t.ref_id), t.etiqueta), (f["id"], f["etiqueta"]))
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, f["url"])
        self.assertContains(pagina, "Abrir línea")

    def test_una_linea_que_el_proveedor_no_reconoce_no_se_vincula(self):
        self.proveedor(ProveedorFalso([self.linea()]))
        e = self.evento()
        self.client.force_login(self.coord)
        r = self.client.post(self.detalle(e), {"accion": "tramite", "tipo": "nueva", "descripcion": "Línea", "linea": str(uuid.uuid4())})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(e.tramites.exists())

    def test_sin_proveedor_la_linea_es_texto_libre(self):
        self.proveedor(None)
        e = self.evento()
        self.client.force_login(self.coord)
        pagina = self.client.get(self.detalle(e))
        self.assertNotContains(pagina, "Línea del sistema")
        self.client.post(self.detalle(e), {"accion": "tramite", "tipo": "reubicacion", "descripcion": "Reubicar", "referencia": "922-55"})
        self.assertContains(self.client.get(self.detalle(e)), "922-55")

    def test_si_el_proveedor_deja_de_ver_la_linea_queda_la_etiqueta_sin_enlace(self):
        f = self.linea()
        self.proveedor(ProveedorFalso([f]))
        e = self.evento()
        self.client.force_login(self.coord)
        self.client.post(self.detalle(e), {"accion": "tramite", "tipo": "reubicacion", "descripcion": "Mover", "linea": f["id"]})
        self.proveedor(ProveedorFalso([]))
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, f["etiqueta"])
        self.assertNotContains(pagina, "Abrir línea")


class VinculosEventosTests(BaseEventos):
    def peticion(self, con_permiso=True, root=False):
        """El proveedor consulta los permisos del usuario en Eventos, no la lista del módulo que atiende la petición."""
        from django.contrib.auth import get_user_model
        ajeno, _ = get_user_model().objects.get_or_create(email="ajeno@example.test")
        return SimpleNamespace(user=self.coord if con_permiso else ajeno, axentra_is_root=root, axentra_permissions_list=[])

    def test_esta_registrado_y_responde_por_vales_y_lineas(self):
        proveedor = integration_registry.resolve("vinculos.eventos")
        self.assertTrue(proveedor.available)
        e = self.evento("Feria")
        vale, linea = str(uuid.uuid4()), str(uuid.uuid4())
        svc.vincular_vale(e, usuario=self.coord, ref_id=vale, etiqueta="VP-1")
        svc.agregar_tramite(e, usuario=self.coord, tipo="nueva", descripcion="Línea", ref_id=linea, etiqueta="922-1")
        (v,) = proveedor.vinculos_de(self.peticion(), "prestamos.vale", vale)
        (l,) = proveedor.vinculos_de(self.peticion(), "telefonia.linea", linea)
        self.assertEqual((v["tipo"], v["id"], v["relacion"]), ("eventos.evento", str(e.pk), "Salió al evento"))
        self.assertEqual(l["relacion"], "Trámite en el evento")
        self.assertEqual(set(v), {"tipo", "id", "etiqueta", "detalle", "estado", "url", "relacion"})
        self.assertTrue(v["url"].endswith(f"/eventos/{e.pk}/"))

    def test_no_responde_sin_permiso_ni_con_tipos_o_ids_raros(self):
        proveedor = integration_registry.resolve("vinculos.eventos")
        e = self.evento()
        vale = str(uuid.uuid4())
        svc.vincular_vale(e, usuario=self.coord, ref_id=vale, etiqueta="VP-1")
        self.assertEqual(proveedor.vinculos_de(self.peticion(con_permiso=False), "prestamos.vale", vale), [])
        self.assertEqual(proveedor.vinculos_de(self.peticion(), "otra.cosa", vale), [])
        self.assertEqual(proveedor.vinculos_de(self.peticion(), "prestamos.vale", "no-es-uuid"), [])
        self.assertEqual(proveedor.vinculos_de(self.peticion(), "prestamos.vale", uuid.uuid4()), [])
        self.assertEqual(len(proveedor.vinculos_de(self.peticion(con_permiso=False, root=True), "prestamos.vale", vale)), 1)

    def test_un_evento_cancelado_sigue_apareciendo_con_su_estado(self):
        e = self.evento()
        vale = str(uuid.uuid4())
        svc.vincular_vale(e, usuario=self.coord, ref_id=vale, etiqueta="VP-1")
        svc.cancelar_evento(e, usuario=self.coord, motivo="Lo suspendieron", avisar=False)
        (v,) = ProveedorVinculos().vinculos_de(self.peticion(), "prestamos.vale", vale)
        self.assertEqual(v["estado"], "Cancelado")
