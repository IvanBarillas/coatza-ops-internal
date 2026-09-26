"""Correos a los técnicos: asignación, cambio, cancelación y quitar. Van por la cola del Core y nunca al propio autor."""
from django.core import mail
from django.test import override_settings

from satelites.eventos import services as svc

from .base import BaseEventos, momento


@override_settings(EVENTOS_PUBLIC_BASE_URL="https://ops.example.test")
class AvisosTests(BaseEventos):
    def correos(self):
        return [(m.to[0], m.subject, m.body) for m in mail.outbox]

    def test_asignar_avisa_al_tecnico_con_su_tramo_y_el_enlace(self):
        e = self.evento(ticket="T-9")
        with self.captureOnCommitCallbacks(execute=True):
            svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, desde=momento(10, 14), hasta=momento(10, 20), nota="Relevo")
        (para, asunto, cuerpo), = self.correos()
        self.assertEqual((para, asunto), ("diego@example.test", "Evento asignado: Feria"))
        for texto in ("Malecón", "Relevo", "Ticket: T-9", "Asignó: Carla Coordinadora", f"https://ops.example.test/app/eventos/eventos/{e.pk}/"):
            self.assertIn(texto, cuerpo)

    def test_no_se_avisa_a_quien_hace_el_cambio_ni_con_avisar_falso(self):
        e = self.evento()
        with self.captureOnCommitCallbacks(execute=True):
            svc.asignar_tecnico(e, usuario=self.diego, tecnico=self.diego)          # se asigna a sí mismo
            svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.vale, avisar=False)
        self.assertEqual(self.correos(), [])

    def test_sin_url_publica_el_correo_no_lleva_enlace(self):
        e = self.evento()
        with self.captureOnCommitCallbacks(execute=True), override_settings(EVENTOS_PUBLIC_BASE_URL=""):
            svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego)
        self.assertNotIn("Detalle:", self.correos()[0][2])

    def test_cambios_que_importan_avisan_a_todos_los_tecnicos_y_los_menores_no(self):
        e = self.evento()
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, avisar=False)
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.vale, avisar=False)
        with self.captureOnCommitCallbacks(execute=True):
            svc.editar_evento(e, usuario=self.coord, nombre=e.nombre, lugar=e.lugar, inicio=e.inicio, fin=e.fin, ticket="T-1")  # solo el ticket
        self.assertEqual(self.correos(), [])
        with self.captureOnCommitCallbacks(execute=True):
            svc.editar_evento(e, usuario=self.coord, nombre=e.nombre, lugar="Parque", inicio=momento(10, 10), fin=e.fin, ticket="T-1")
        self.assertEqual(sorted(p for p, _, _ in self.correos()), ["diego@example.test", "vale@example.test"])
        self.assertIn("lugar", self.correos()[0][2])

    def test_cancelar_avisa_con_el_motivo_y_quitar_avisa_al_afectado(self):
        e = self.evento()
        a, _ = svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.diego, avisar=False)
        with self.captureOnCommitCallbacks(execute=True):
            svc.quitar_tecnico(a, usuario=self.coord)
        self.assertEqual(self.correos()[0][:2], ("diego@example.test", "Asignación quitada: Feria"))
        mail.outbox.clear()
        svc.asignar_tecnico(e, usuario=self.coord, tecnico=self.vale, avisar=False)
        with self.captureOnCommitCallbacks(execute=True):
            svc.cancelar_evento(e, usuario=self.coord, motivo="Lo suspendieron por lluvia")
        (para, asunto, cuerpo), = self.correos()
        self.assertEqual((para, asunto), ("vale@example.test", "Evento cancelado: Feria"))
        self.assertIn("Lo suspendieron por lluvia", cuerpo)

    def test_un_correo_fallido_no_deshace_el_cambio_al_no_haber_correo(self):
        from django.contrib.auth import get_user_model
        sin = get_user_model().objects.create_user(email="sin@example.test", first_name="Sin", last_name="Correo")
        sin.email = ""
        e = self.evento()
        with self.captureOnCommitCallbacks(execute=True):
            a, _ = svc.asignar_tecnico(e, usuario=self.coord, tecnico=sin)
        self.assertTrue(a.pk)
        self.assertEqual(self.correos(), [])
