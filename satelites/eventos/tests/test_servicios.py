from django.core.exceptions import ValidationError

from satelites.eventos import services as svc
from satelites.eventos.models import Bitacora, Evento

from .base import BaseEventos, momento


class ServiciosEventosTests(BaseEventos):
    def test_crear_valida_fechas_y_deja_bitacora(self):
        with self.assertRaises(ValidationError):
            self.evento(inicio=momento(10, 9), fin=momento(10, 9))
        e = self.evento(ticket=" T-1 ")
        self.assertEqual((e.estatus, e.ticket), ("programado", "T-1"))
        self.assertEqual(e.bitacora.get().accion, "creado")

    def test_varios_tecnicos_y_relevos_por_tramo(self):
        e = self.evento()
        a1, avisos = svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, desde=momento(10, 9), hasta=momento(10, 15))
        self.assertEqual(avisos, [])
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.vale, desde=momento(10, 14), hasta=momento(10, 22), nota="Relevo")
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, desde=momento(10, 18), hasta=momento(10, 20))  # segundo tramo de Diego
        self.assertEqual(e.asignaciones.count(), 3)
        with self.assertRaises(ValidationError):  # tramo traslapado de la misma persona en el mismo evento
            svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, desde=momento(10, 12), hasta=momento(10, 16))
        with self.assertRaises(ValidationError):
            svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.vale, desde=momento(10, 20), hasta=momento(10, 19))
        svc.quitar_tecnico(a1, usuario=self.coord)
        self.assertEqual(e.asignaciones.count(), 2)

    def test_sin_fechas_cubre_todo_el_evento(self):
        e = self.evento()
        a, _ = svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego)
        self.assertEqual((a.desde, a.hasta), (e.inicio, e.fin))

    def test_empalme_con_otro_evento_solo_avisa(self):
        e1, e2 = self.evento("Uno"), self.evento("Dos", inicio=momento(10, 20), fin=momento(10, 23))
        svc.asignar_tecnico(e1, usuario=self.coord, tecnico=self.diego)
        a, avisos = svc.asignar_tecnico(e2, usuario=self.coord, tecnico=self.diego)
        self.assertTrue(a.pk)
        self.assertEqual(len(avisos), 1)
        self.assertIn("«Uno»", avisos[0])
        svc.cancelar_evento(e1, usuario=self.coord, motivo="Ya no se hará")
        self.assertEqual(svc.empalmes(self.diego, a.desde, a.hasta, excluir=e2), [])  # un evento cancelado no cuenta

    def test_ciclo_de_estados(self):
        e = self.evento()
        svc.iniciar_evento(e, usuario=self.coord)
        with self.assertRaises(ValidationError):
            svc.iniciar_evento(e, usuario=self.coord)
        svc.concluir_evento(e, usuario=self.coord, notas="Todo bien")
        self.assertEqual((e.estatus, e.notas_cierre), ("concluido", "Todo bien"))
        for accion in (lambda: svc.cancelar_evento(e, usuario=self.coord, motivo="Motivo largo"), lambda: svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego),
                       lambda: svc.vincular_vale(e, usuario=self.coord, referencia="V-1"), lambda: svc.editar_evento(e, usuario=self.coord, nombre="X", lugar="Y", inicio=e.inicio, fin=e.fin)):
            with self.assertRaises(ValidationError):
                accion()

    def test_cancelar_exige_motivo(self):
        e = self.evento()
        with self.assertRaises(ValidationError):
            svc.cancelar_evento(e, usuario=self.coord, motivo="no")
        svc.cancelar_evento(e, usuario=self.coord, motivo="Lo suspendieron")
        e.refresh_from_db()
        self.assertEqual((e.estatus, e.motivo_cancelacion), ("cancelado", "Lo suspendieron"))

    def test_vales_tramites_y_notas(self):
        e = self.evento()
        v = svc.vincular_vale(e, usuario=self.coord, referencia=" V-12 ", nota="Bocinas")
        self.assertEqual(v.referencia, "V-12")
        with self.assertRaises(ValidationError):
            svc.vincular_vale(e, usuario=self.coord, referencia="v-12")
        with self.assertRaises(ValidationError):
            svc.vincular_vale(e, usuario=self.coord, referencia="  ")
        t = svc.agregar_tramite(e, usuario=self.coord, tipo="nueva", descripcion="Línea para el módulo")
        svc.cambiar_estado_tramite(t, usuario=self.coord, estado="listo")
        t.refresh_from_db()
        self.assertEqual(t.estado, "listo")
        with self.assertRaises(ValidationError):
            svc.cambiar_estado_tramite(t, usuario=self.coord, estado="raro")
        svc.agregar_nota(e, usuario=self.diego, texto="Llegué al sitio")
        with self.assertRaises(ValidationError):
            svc.agregar_nota(e, usuario=self.diego, texto=" ")
        self.assertTrue(Bitacora.objects.filter(evento=e, accion="nota", usuario_nombre="Diego Técnico").exists())
        svc.desvincular_vale(v, usuario=self.coord)
        self.assertFalse(e.vales.exists())

    def test_editar_registra_que_cambio(self):
        e = self.evento()
        svc.editar_evento(e, usuario=self.coord, nombre="Feria del libro", lugar=e.lugar, inicio=e.inicio, fin=e.fin, ticket="T-9")
        self.assertIn("nombre", e.bitacora.filter(accion="editado").get().detalle)
        self.assertIn("ticket", e.bitacora.filter(accion="editado").get().detalle)

    def test_calendario_muestra_el_evento_en_cada_dia_que_abarca_y_filtra_por_tecnico(self):
        e = self.evento(inicio=momento(10, 20), fin=momento(12, 2))
        otro = self.evento("Otro", inicio=momento(11, 9), fin=momento(11, 10))
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego)
        dias = {d["fecha"].day: d["eventos"] for s in svc.calendario_mes(2030, 9) for d in s if d["en_mes"]}
        self.assertEqual([len(dias[n]) for n in (9, 10, 11, 12, 13)], [0, 1, 2, 1, 0])
        solo = {d["fecha"].day: d["eventos"] for s in svc.calendario_mes(2030, 9, self.diego.pk) for d in s if d["en_mes"]}
        self.assertEqual([len(solo[n]) for n in (10, 11, 12)], [1, 1, 1])
        self.assertNotIn(otro, solo[11])
        svc.cancelar_evento(e, usuario=self.coord, motivo="Suspendido por lluvia")
        self.assertEqual(sum(len(d["eventos"]) for s in svc.calendario_mes(2030, 9) for d in s if d["en_mes"] and d["fecha"].day == 10), 0)
