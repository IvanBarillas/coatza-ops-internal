import datetime

from django.core.exceptions import ValidationError

from satelites.telefonia import services
from satelites.telefonia.models import Evidencia, Linea, Movimiento, Reporte

from .base import HOY, PNG, BaseTelefonia, png


class ReporteServiciosTests(BaseTelefonia):
    def reporte(self, **extra):
        datos = dict(usuario=self.operador, linea=self.linea, folio="11986221", levantado=HOY, detalle="Sin tono",
                     contacto_nombre="Ana", contacto_telefono="9212223344")
        return services.crear_reporte(**{**datos, **extra})

    def test_crear_guarda_snapshot_bitacora_y_normaliza_el_folio(self):
        r = self.reporte(folio="  imm ct001147 ")
        self.assertEqual((r.linea_texto, r.sitio_texto, r.estatus), ("9212165053", "Línea Allende", "pendiente"))
        self.assertEqual(r.folio, "imm ct001147")
        self.assertEqual(r.folio_normalizado, "IMMCT001147")
        self.assertEqual(r.movimientos.get().tipo, "creado")

    def test_el_folio_no_se_repite_aunque_cambien_espacios_o_mayusculas(self):
        self.reporte(folio="IMMCT001147")
        with self.assertRaises(ValidationError):
            self.reporte(folio="immct 001147")

    def test_validaciones_de_creacion(self):
        with self.assertRaises(ValidationError):
            self.reporte(folio=" ")
        with self.assertRaises(ValidationError):
            self.reporte(levantado=HOY + datetime.timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.reporte(contacto_nombre="", contacto_telefono="")
        inactiva = Linea.objects.create(identificador="X-1", sitio="Baja", is_active=False)
        with self.assertRaises(ValidationError):
            self.reporte(linea=inactiva)

    def test_el_responsable_llena_el_contacto_si_no_se_escribio(self):
        r = self.reporte(contacto_nombre="", contacto_telefono="", responsable=self.tecnico)
        self.assertEqual((r.contacto_nombre, r.contacto_telefono, r.responsable_nombre), ("Tomás Técnico", "9211110000", "Tomás Técnico"))

    def test_comentarios_son_bitacora_y_no_se_permiten_en_cancelados(self):
        r = self.reporte()
        services.comentar(r, usuario=self.tecnico, texto="Fui hoy pero no había nadie")
        services.comentar(r, usuario=self.tecnico, texto="Regreso mañana")
        self.assertEqual([m.texto for m in r.movimientos.filter(tipo="comentario")], ["Fui hoy pero no había nadie", "Regreso mañana"])
        with self.assertRaises(ValidationError):
            services.comentar(r, usuario=self.tecnico, texto=" ")
        services.cancelar(r, usuario=self.operador, motivo="Duplicado del anterior")
        with self.assertRaises(ValidationError):
            services.comentar(r, usuario=self.tecnico, texto="Otro comentario")

    def test_atender_registra_fecha_dias_y_valida(self):
        r = self.reporte(levantado=HOY - datetime.timedelta(days=4))
        with self.assertRaises(ValidationError):
            services.marcar_atendido(r, usuario=self.tecnico, fecha=HOY + datetime.timedelta(days=1))
        with self.assertRaises(ValidationError):
            services.marcar_atendido(r, usuario=self.tecnico, fecha=HOY - datetime.timedelta(days=9))
        services.marcar_atendido(r, usuario=self.tecnico, comentario="Ya funciona")
        r.refresh_from_db()
        self.assertEqual((r.estatus, r.atendido, r.dias_abierto), ("atendido", HOY, 4))
        self.assertEqual(r.movimientos.get(tipo="atendido").datos["dias"], 4)
        with self.assertRaises(ValidationError):
            services.marcar_atendido(r, usuario=self.tecnico)

    def test_cancelar_y_reabrir_exigen_motivo(self):
        r = self.reporte()
        with self.assertRaises(ValidationError):
            services.cancelar(r, usuario=self.operador, motivo="no")
        services.cancelar(r, usuario=self.operador, motivo="Telmex lo cerró")
        with self.assertRaises(ValidationError):
            services.cancelar(r, usuario=self.operador, motivo="Otra vez cancelado")
        services.reabrir(r, usuario=self.operador, motivo="Volvió a fallar")
        r.refresh_from_db()
        self.assertEqual((r.estatus, r.atendido, r.motivo_cancelacion), ("pendiente", None, ""))

    def test_la_evidencia_es_opcional_valida_formato_y_no_se_repite(self):
        r = self.reporte()
        services.marcar_atendido(r, usuario=self.tecnico)  # sin evidencia: permitido
        e = services.subir_evidencia(r, usuario=self.tecnico, archivo=png(), tipo="velocidad")
        self.assertEqual((e.content_type, e.tipo, e.tamano), ("image/png", "velocidad", len(PNG)))
        self.assertEqual(r.movimientos.filter(tipo="evidencia").count(), 1)
        with self.assertRaises(ValidationError):
            services.subir_evidencia(r, usuario=self.tecnico, archivo=png())  # mismo archivo
        from django.core.files.uploadedfile import SimpleUploadedFile

        with self.assertRaises(ValidationError):
            services.subir_evidencia(r, usuario=self.tecnico, archivo=SimpleUploadedFile("x.exe", b"MZ\x90\x00malo"))
        with self.assertRaises(ValidationError):
            services.subir_evidencia(r, usuario=self.tecnico, archivo=SimpleUploadedFile("x.png", PNG[:12] + b"roto"))
        with self.assertRaises(ValidationError):
            services.subir_evidencia(r, usuario=self.tecnico, archivo=png("v.png", PNG), tipo="rara")

    def test_editar_deja_antes_y_despues_y_valida_folio_y_fechas(self):
        r = self.reporte()
        otro = self.reporte(folio="OTRO-1")
        with self.assertRaises(ValidationError):
            services.editar_reporte(r, usuario=self.operador, cambios={"folio": "otro-1"})
        with self.assertRaises(ValidationError):
            services.editar_reporte(r, usuario=self.operador, cambios={"levantado": HOY + datetime.timedelta(days=2)})
        with self.assertRaises(ValidationError):
            services.editar_reporte(r, usuario=self.operador, cambios={"linea": self.linea})
        with self.assertRaises(ValidationError):
            services.editar_reporte(r, usuario=self.operador, cambios={"detalle": r.detalle})
        services.editar_reporte(r, usuario=self.operador, cambios={"folio": "11986299", "contacto_telefono": "9219998877"}, motivo="Error de captura")
        r.refresh_from_db()
        cambios = r.movimientos.get(tipo="editado").datos["cambios"]
        self.assertEqual(cambios["Folio de Telmex"], {"antes": "11986221", "despues": "11986299"})
        self.assertEqual(r.folio_normalizado, "11986299")

    def test_asignar_responsable(self):
        r = self.reporte()
        services.asignar_responsable(r, usuario=self.operador, responsable=self.tecnico)
        r.refresh_from_db()
        self.assertEqual(r.responsable, self.tecnico)
        with self.assertRaises(ValidationError):
            services.asignar_responsable(r, usuario=self.operador, responsable=self.tecnico)

    def test_la_bitacora_es_de_solo_escritura(self):
        r = self.reporte()
        m = r.movimientos.get()
        m.texto = "cambiado"
        with self.assertRaises(ValueError):
            m.save()
        with self.assertRaises(ValueError):
            m.delete()

    def test_semaforo_por_dias_abiertos(self):
        self.assertEqual([self.reporte(folio=f"F{d}", levantado=HOY - datetime.timedelta(days=d)).color for d in (0, 3, 7, 12)], ["verde", "ambar", "rojo", "rojo"])
