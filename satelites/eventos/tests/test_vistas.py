from django.contrib.messages import get_messages
from django.urls import reverse

from satelites.eventos import services as svc
from satelites.eventos.models import Asignacion, Evento

from .base import BaseEventos, momento


def url(nombre, *args):
    return reverse(f"eventos:{nombre}", args=args)


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


def fecha(dt):
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M")


class VistasEventosTests(BaseEventos):
    def datos_evento(self, **extra):
        return {"nombre": "Concierto", "lugar": "Malecón", "inicio": "2030-09-10T18:00", "fin": "2030-09-10T23:00", "ticket": "T-5", "descripcion": "Red y sonido", **extra}

    def test_inicio_y_menu_por_rol(self):
        self.client.force_login(self.diego)
        self.assertRedirects(self.client.get(url("inicio")), url("mis_eventos"), fetch_redirect_response=False)
        self.assertEqual([i["name"] for i in self.client.get(url("mis_eventos")).context["sidebar_items"]], ["Mis eventos", "Calendario", "Eventos"])
        self.client.force_login(self.coord)
        self.assertEqual([i["name"] for i in self.client.get(url("calendario")).context["sidebar_items"]], ["Mis eventos", "Calendario", "Eventos", "Nuevo evento"])
        self.client.force_login(self.lector)
        self.assertRedirects(self.client.get(url("inicio")), url("calendario"), fetch_redirect_response=False)
        self.assertIn(self.client.get(url("mis_eventos")).status_code, (302, 403))

    def test_solo_el_coordinador_crea_edita_y_gestiona(self):
        self.client.force_login(self.diego)
        self.assertIn(self.client.get(url("evento_crear")).status_code, (302, 403))
        self.assertIn(self.client.post(url("evento_crear"), self.datos_evento()).status_code, (302, 403))
        self.assertFalse(Evento.objects.exists())
        e = self.evento()
        for accion, extra in (("asignar", {"tecnico": self.diego.pk}), ("vale", {"referencia": "V-1"}), ("iniciar", {}), ("cancelar", {"motivo": "Motivo largo"})):
            self.assertEqual(self.client.post(url("evento_detalle", e.pk), {"accion": accion, **extra}).status_code, 403)
        e.refresh_from_db()
        self.assertEqual((e.estatus, e.asignaciones.count(), e.vales.count()), ("programado", 0, 0))

    def test_crear_evento_con_ticket_y_editar(self):
        self.client.force_login(self.coord)
        r = self.client.post(url("evento_crear"), self.datos_evento())
        e = Evento.objects.get()
        self.assertRedirects(r, url("evento_detalle", e.pk), fetch_redirect_response=False)
        self.assertEqual((e.ticket, e.creado_por), ("T-5", self.coord))
        self.assertContains(self.client.get(url("evento_editar", e.pk)), "2030-09-10T18:00")
        self.client.post(url("evento_editar", e.pk), self.datos_evento(nombre="Concierto de gala"))
        e.refresh_from_db()
        self.assertEqual(e.nombre, "Concierto de gala")
        malo = self.client.post(url("evento_crear"), self.datos_evento(fin="2030-09-10T17:00"))
        self.assertEqual(malo.status_code, 200)
        self.assertIn("fin", malo.context["form"].errors)
        self.assertEqual(Evento.objects.count(), 1)

    def test_asignar_varios_tecnicos_avisa_de_empalmes_y_quita(self):
        otro = self.evento("Otro", inicio=momento(10, 20), fin=momento(10, 23))
        svc.asignar_tecnico(otro, usuario=self.coord, tecnico=self.diego)
        e = self.evento()
        self.client.force_login(self.coord)
        r = self.client.post(url("evento_detalle", e.pk), {"accion": "asignar", "tecnico": self.diego.pk, "desde": "2030-09-10T09:00", "hasta": "2030-09-10T22:00"})
        self.assertRedirects(r, url("evento_detalle", e.pk), fetch_redirect_response=False)
        textos = mensajes(r)
        self.assertTrue(any("Técnico asignado" in t for t in textos))
        self.assertTrue(any("se empalma" in t for t in textos))
        self.client.post(url("evento_detalle", e.pk), {"accion": "asignar", "tecnico": self.vale.pk})
        self.assertEqual(e.asignaciones.count(), 2)
        pagina = self.client.get(url("evento_detalle", e.pk))
        self.assertContains(pagina, "También en «Otro»")
        self.client.post(url("evento_detalle", e.pk), {"accion": "quitar_tecnico", "id": Asignacion.objects.filter(evento=e, tecnico=self.diego).get().pk})
        self.assertEqual(e.asignaciones.count(), 1)
        ajeno = Asignacion.objects.get(evento=otro)
        self.assertEqual(self.client.post(url("evento_detalle", e.pk), {"accion": "quitar_tecnico", "id": ajeno.pk}).status_code, 404)  # no de otro evento
        self.assertTrue(Asignacion.objects.filter(pk=ajeno.pk).exists())

    def test_solo_asigna_usuarios_del_modulo(self):
        from django.contrib.auth import get_user_model
        ajeno = get_user_model().objects.create_user(email="ajeno@example.test", first_name="Ajeno", last_name="Sin acceso")
        e = self.evento()
        self.client.force_login(self.coord)
        r = self.client.post(url("evento_detalle", e.pk), {"accion": "asignar", "tecnico": ajeno.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(e.asignaciones.exists())

    def test_vales_tramites_estado_y_notas(self):
        e = self.evento()
        self.client.force_login(self.coord)
        detalle = url("evento_detalle", e.pk)
        self.client.post(detalle, {"accion": "vale", "referencia": "V-7", "nota": "Bocinas"})
        self.assertContains(self.client.get(detalle), "V-7")
        dup = self.client.post(detalle, {"accion": "vale", "referencia": "v-7"}, follow=True)
        self.assertContains(dup, "ya está vinculado")
        self.client.post(detalle, {"accion": "tramite", "tipo": "reubicacion", "descripcion": "Reubicar enlace", "referencia": "922-1"})
        t = e.tramites.get()
        self.client.post(detalle, {"accion": "tramite_estado", "id": t.pk, "estado": "en_tramite"})
        t.refresh_from_db()
        self.assertEqual(t.estado, "en_tramite")
        self.client.post(detalle, {"accion": "nota", "texto": "Se probó el enlace"})
        self.assertContains(self.client.get(detalle), "Se probó el enlace")
        self.client.post(detalle, {"accion": "iniciar"})
        self.client.post(detalle, {"accion": "concluir", "notas": "Sin novedades"})
        e.refresh_from_db()
        self.assertEqual((e.estatus, e.notas_cierre), ("concluido", "Sin novedades"))
        self.assertContains(self.client.get(detalle), "Sin novedades")
        self.assertEqual(self.client.get(url("evento_editar", e.pk)).status_code, 302)  # concluido: ya no se edita

    def test_el_tecnico_agrega_notas_pero_no_gestiona(self):
        e = self.evento()
        self.client.force_login(self.diego)
        self.client.post(url("evento_detalle", e.pk), {"accion": "nota", "texto": "En sitio"})
        self.assertTrue(e.bitacora.filter(accion="nota", usuario=self.diego).exists())
        pagina = self.client.get(url("evento_detalle", e.pk))
        self.assertNotContains(pagina, "Agregar técnico")
        self.client.force_login(self.lector)
        self.assertEqual(self.client.post(url("evento_detalle", e.pk), {"accion": "nota", "texto": "Intento"}).status_code, 403)

    def test_mis_eventos_ordena_el_proximo_y_marca_empalmes(self):
        cerca = self.evento("Cerca", inicio=momento(10, 9), fin=momento(10, 12))
        lejos = self.evento("Lejos", inicio=momento(20, 9), fin=momento(20, 12))
        choca = self.evento("Choca", inicio=momento(10, 11), fin=momento(10, 13))
        for ev in (lejos, cerca, choca):
            svc.asignar_tecnico(ev, usuario=self.coord, tecnico=self.diego)
        self.client.force_login(self.diego)
        pagina = self.client.get(url("mis_eventos"))
        self.assertEqual([a.evento.nombre for a in pagina.context["proximas"]], ["Cerca", "Choca", "Lejos"])
        self.assertEqual(pagina.context["proxima"].evento, cerca)
        self.assertEqual([a.empalmada for a in pagina.context["proximas"]], [True, True, False])
        self.assertContains(pagina, "Se empalma con otro evento")
        self.client.force_login(self.vale)
        self.assertIsNone(self.client.get(url("mis_eventos")).context["proxima"])

    def test_lista_filtra_por_estado_tecnico_y_texto(self):
        e1, e2 = self.evento("Feria del libro", ticket="T-88"), self.evento("Concierto")
        svc.asignar_tecnico(e1, usuario=self.coord, tecnico=self.diego)
        svc.cancelar_evento(e2, usuario=self.coord, motivo="Suspendido por lluvia")
        self.client.force_login(self.lector)
        lista = lambda **kw: [e.pk for e in self.client.get(url("eventos"), kw).context["pagina"]]
        self.assertEqual(lista(), [e1.pk])
        self.assertEqual(lista(estado="cancelados"), [e2.pk])
        self.assertEqual(set(lista(estado="todos")), {e1.pk, e2.pk})
        self.assertEqual(lista(estado="todos", q="T-88"), [e1.pk])
        self.assertEqual(lista(estado="todos", tecnico=str(self.diego.pk)), [e1.pk])
        self.assertEqual({x["clave"]: x["total"] for x in self.client.get(url("eventos")).context["estados"]}, {"abiertos": 1, "concluidos": 0, "cancelados": 1, "todos": 2})

    def test_calendario_y_parametros_invalidos(self):
        e = self.evento()
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego)
        svc.asignar_tecnico(self.evento("Sesión", inicio=momento(20, 9), fin=momento(20, 10)), usuario=self.coord, tecnico=self.vale)
        self.client.force_login(self.lector)
        pagina = self.client.get(url("calendario"), {"anio": 2030, "mes": 9})
        self.assertContains(pagina, "Feria")
        self.assertNotContains(self.client.get(url("calendario"), {"anio": 2030, "mes": 9, "tecnico": str(self.vale.pk)}), "Feria")
        self.assertEqual(self.client.get(url("calendario"), {"anio": "x", "mes": "99", "tecnico": "nada"}).status_code, 200)

    def test_carga_parcial_htmx(self):
        e = self.evento()
        self.client.force_login(self.coord)
        parcial = self.client.get(url("evento_detalle", e.pk), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="page-content")
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, "Feria")
