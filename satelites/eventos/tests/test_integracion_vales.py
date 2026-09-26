"""Eventos consume la capacidad `prestamos.vales` por nombre: con proveedor, sin proveedor o con un proveedor que no reconoce el vale."""
import uuid

from django.urls import reverse

from apps.shared.module_sdk.integrations import integration_registry

from .base import BaseEventos

NOMBRE = "prestamos.vales"


class ProveedorFalso:
    available = True

    def __init__(self, fichas):
        self.fichas = {f["id"]: f for f in fichas}

    def resolver(self, request, ref_id):
        return self.fichas.get(str(ref_id))

    def buscar(self, request, texto="", *, limite=20, solo_abiertos=True):
        return list(self.fichas.values())[:limite]


def ficha(etiqueta="VP-001/2030 · Egresos", estado="vigente"):
    pk = str(uuid.uuid4())
    return {"tipo": "prestamos.vale", "id": pk, "etiqueta": etiqueta, "detalle": "Bocinas, consola", "estado": estado, "url": f"/vale/{pk}/"}


class IntegracionValesTests(BaseEventos):
    def proveedor(self, proveedor):
        """Sustituye (o quita, con None) el proveedor mientras dura la prueba."""
        antes = integration_registry._providers.get(NOMBRE)
        self.addCleanup(lambda: integration_registry._providers.__setitem__(NOMBRE, antes) if antes is not None else integration_registry._providers.pop(NOMBRE, None))
        if proveedor is None:
            integration_registry._providers.pop(NOMBRE, None)
        else:
            integration_registry.register(NOMBRE, proveedor, replace=True)

    def detalle(self, e):
        return reverse("eventos:evento_detalle", args=[e.pk])

    def test_con_proveedor_se_elige_el_vale_y_se_guarda_uuid_y_etiqueta(self):
        f = ficha()
        self.proveedor(ProveedorFalso([f]))
        e = self.evento()
        self.client.force_login(self.coord)
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, "Vale del sistema")
        self.assertContains(pagina, "VP-001/2030")
        self.client.post(self.detalle(e), {"accion": "vale", "vale": f["id"], "nota": "Sonido"})
        v = e.vales.get()
        self.assertEqual((str(v.ref_id), v.etiqueta, v.nota), (f["id"], f["etiqueta"], "Sonido"))
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, f["url"])           # botón para abrirlo
        self.assertContains(pagina, "Abrir vale")
        self.assertContains(pagina, "vigente")
        self.assertNotContains(pagina, f"<option value=\"{f['id']}\"")  # ya vinculado: no se ofrece otra vez

    def test_el_vale_que_el_proveedor_no_reconoce_no_se_vincula(self):
        self.proveedor(ProveedorFalso([ficha()]))
        e = self.evento()
        self.client.force_login(self.coord)
        r = self.client.post(self.detalle(e), {"accion": "vale", "vale": str(uuid.uuid4())})
        self.assertEqual(r.status_code, 200)  # el formulario rechaza la opción que no se ofreció
        self.assertFalse(e.vales.exists())

    def test_si_el_proveedor_deja_de_ver_el_vale_queda_el_texto_sin_enlace(self):
        f = ficha()
        self.proveedor(ProveedorFalso([f]))
        e = self.evento()
        self.client.force_login(self.coord)
        self.client.post(self.detalle(e), {"accion": "vale", "vale": f["id"]})
        self.proveedor(ProveedorFalso([]))  # ya no lo ve (permiso, borrado…)
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, f["etiqueta"])
        self.assertNotContains(pagina, "Abrir vale")

    def test_sin_proveedor_todo_funciona_con_texto_libre(self):
        self.proveedor(None)
        e = self.evento()
        self.client.force_login(self.coord)
        pagina = self.client.get(self.detalle(e))
        self.assertNotContains(pagina, "Vale del sistema")
        self.assertContains(pagina, "Vale (número o UUID)")
        self.client.post(self.detalle(e), {"accion": "vale", "referencia": "V-55", "nota": "Cables"})
        self.assertEqual(e.vales.get().referencia, "V-55")
        pagina = self.client.get(self.detalle(e))
        self.assertContains(pagina, "V-55")
        self.assertNotContains(pagina, "Abrir vale")

    def test_hay_que_elegir_un_vale_o_escribirlo(self):
        self.proveedor(ProveedorFalso([ficha()]))
        e = self.evento()
        self.client.force_login(self.coord)
        r = self.client.post(self.detalle(e), {"accion": "vale"})
        self.assertContains(r, "Elija un vale o escriba su número")
        self.assertFalse(e.vales.exists())
