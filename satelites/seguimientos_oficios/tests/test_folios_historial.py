import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.security.models import Dependencia
from satelites.seguimientos_oficios.models import Direccion, Documento, HistorialDocumento, Nomenclatura
from satelites.seguimientos_oficios.services import cancelar_documento, crear_documento, marcar_entregado


class FoliosYHistorialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.titular = get_user_model().objects.create_user(
            email="juan@example.test", first_name="Juan", last_name="Pérez"
        )
        cls.dep = Dependencia.objects.create(nombre="Innovación", encargado_departamento=cls.titular)
        cls.innovacion = Direccion.objects.create(nombre="Innovación", dependencia_uuid=cls.dep.pk, folio_manual=False)
        cls.egresos = Direccion.objects.create(nombre="Egresos", folio_manual=False)
        cls.sin_prefijo = Direccion.objects.create(nombre="Sin nomenclatura", folio_manual=False)
        for direccion, clase, plantilla in (
            (cls.innovacion, "dictamen_alta", "IN-{n:03d}/{anio}"),
            (cls.innovacion, "vale_prestamo", "VP-IN-{n}/{anio}"),
            (cls.egresos, "dictamen_alta", "EG-{n:03d}/{anio}"),
        ):
            Nomenclatura.objects.create(direccion=direccion, clase=clase, plantilla=plantilla)

    def nuevo(self, direccion=None, sentido="enviado", fecha=None, clase="dictamen_alta", **extra):
        return crear_documento(
            usuario=self.titular, direccion=direccion or self.innovacion, sentido=sentido,
            clase=clase, contraparte="Tesorería", asunto="Alta de equipo",
            fecha=fecha or datetime.date(2026, 9, 1), **extra,
        )

    def test_folio_consecutivo_por_direccion_y_anio(self):
        self.assertEqual(self.nuevo().folio, "IN-001/2026")
        self.assertEqual(self.nuevo().folio, "IN-002/2026")
        self.assertEqual(self.nuevo(self.egresos).folio, "EG-001/2026")
        self.assertEqual(self.nuevo(fecha=datetime.date(2027, 1, 5)).folio, "IN-001/2027")

    def test_cada_clase_lleva_su_propia_serie(self):
        self.assertEqual(self.nuevo().folio, "IN-001/2026")
        self.assertEqual(self.nuevo(clase="vale_prestamo").folio, "VP-IN-1/2026")
        self.assertEqual(self.nuevo(clase="vale_prestamo").folio, "VP-IN-2/2026")
        self.assertEqual(self.nuevo().folio, "IN-002/2026")

    def test_plantilla_invalida_se_rechaza(self):
        for mala in ("SIN-NUMERO", "IN-{n.__class__}", "{n}{x}"):
            with self.assertRaises(ValidationError):
                Nomenclatura(direccion=self.egresos, clase="oficio", plantilla=mala).clean()

    def test_recibido_conserva_folio_del_remitente(self):
        documento = self.nuevo(sentido="recibido", folio="TES/45/2026")
        self.assertEqual(documento.folio, "TES/45/2026")
        self.assertIsNone(documento.consecutivo)

    def test_enviado_exige_nomenclatura(self):
        with self.assertRaises(ValidationError):
            self.nuevo(self.sin_prefijo)

    def test_director_es_snapshot_y_no_cambia_con_el_organigrama(self):
        documento = self.nuevo()
        self.assertEqual(documento.director_nombre, "Juan Pérez")
        pedro = get_user_model().objects.create_user(email="pedro@example.test", first_name="Pedro")
        self.dep.encargado_departamento = pedro
        self.dep.save()
        documento.refresh_from_db()
        self.assertEqual(documento.director_nombre, "Juan Pérez")
        self.assertEqual(self.nuevo().director_nombre, "Pedro")

    def test_historial_registra_creacion_y_es_solo_escritura(self):
        documento = self.nuevo()
        entrada = documento.historial.get()
        self.assertEqual(entrada.accion, "creado")
        self.assertEqual(entrada.datos["director"], "Juan Pérez")
        self.assertEqual(entrada.usuario_nombre, "Juan Pérez")
        entrada.datos = {}
        with self.assertRaises(ValueError):
            entrada.save()
        with self.assertRaises(ValueError):
            entrada.delete()
        self.assertEqual(HistorialDocumento.objects.count(), 1)

    def test_campos_inmutables(self):
        documento = self.nuevo()
        for campo, valor in (("folio", "IN-999/2026"), ("director_nombre", "Otro")):
            setattr(documento, campo, valor)
            with self.assertRaises(ValueError):
                documento.save()
            documento.refresh_from_db()
        documento.asunto = "Asunto corregido"
        documento.save()
        self.assertEqual(Documento.objects.get(pk=documento.pk).asunto, "Asunto corregido")

    def test_entrega_y_cancelacion_dejan_historial(self):
        documento = self.nuevo()
        self.assertEqual(documento.estado, "generado")
        marcar_entregado(documento, usuario=self.titular, fecha_entrega=datetime.date(2026, 9, 3), receptor="Recepción Tesorería")
        documento.refresh_from_db()
        self.assertEqual((documento.estado, documento.receptor_entrega), ("entregado", "Recepción Tesorería"))
        with self.assertRaises(ValidationError):
            marcar_entregado(documento, usuario=self.titular, fecha_entrega=datetime.date(2026, 9, 3), receptor="X")
        cancelar_documento(documento, usuario=self.titular, motivo="Error en el número de serie del equipo X")
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "cancelado")
        self.assertEqual([h.accion for h in documento.historial.all()], ["creado", "editado", "eliminado"])
        with self.assertRaises(ValidationError):
            cancelar_documento(documento, usuario=self.titular, motivo="Otro motivo suficientemente largo")

    def test_cancelar_exige_motivo(self):
        documento = self.nuevo()
        for motivo in ("", "   ", "corto"):
            with self.assertRaises(ValidationError):
                cancelar_documento(documento, usuario=self.titular, motivo=motivo)

    def test_concluido_solo_se_cancela_con_permiso_especial(self):
        documento = self.nuevo()
        Documento.objects.filter(pk=documento.pk).update(estado="concluido")
        motivo = "Error en el número de serie del equipo X"
        with self.assertRaises(ValidationError):
            cancelar_documento(documento, usuario=self.titular, motivo=motivo)
        cancelar_documento(documento, usuario=self.titular, motivo=motivo, puede_cancelar_concluido=True)
        documento.refresh_from_db()
        self.assertEqual(documento.estado, "cancelado")

    def test_documento_no_se_elimina(self):
        documento = self.nuevo()
        with self.assertRaises(ValueError):
            documento.delete()
