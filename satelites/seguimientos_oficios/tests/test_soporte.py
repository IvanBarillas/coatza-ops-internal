from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Bien, Dictamen, Direccion, Documento, HistorialBien, Nomenclatura
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
import datetime

from satelites.seguimientos_oficios.soporte import services as svc

from .base import SOLO_OFICIOS, BaseAdjuntos


class SoporteBase(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        Direccion.objects.filter(pk=self.direccion.pk).update(soporte_habilitado=True)
        self.direccion.refresh_from_db()
        for clase, prefijo in (("diagnostico_tecnico", "DT"), ("dictamen_baja", "DIB"), ("dictamen_alta", "DIA"), ("resguardo", "RES")):
            Nomenclatura.objects.create(direccion=self.direccion, clase=clase, plantilla=prefijo + "-STI-TM{n:03d}-{anio2}")
        UserAppRole.objects.filter(user=self.user).update(role="soporte", permissions_list=P.ROLE_MAPPING["soporte"])
        self.laptop = Bien.objects.create(direccion=self.direccion, nombre="Laptop", identificador="LT-1", marca_modelo="Dell 5420")
        self.client.force_login(self.user)

    def baja(self, equipos=None, **extra):
        return svc.emitir_baja(
            usuario=self.user, direccion=self.direccion, contraparte="Tesorería", ticket="1234",
            equipos=equipos or [{"equipo": "Laptop", "bien": self.laptop, "serie": "LT-1"}],
            datos={"diagnostico": "No enciende", "clasificacion": "no_reparable", "disposicion": "destruccion", "solicito": "Ana"},
            elaboro_nombre="Técnico", elaboro_cargo="Técnico de Soporte en TI", autoriza_nombre="Jefe", autoriza_cargo="Director", **extra,
        )


class NomenclaturaConAnioCortoTests(SoporteBase):
    def test_anio2_formatea_e_interpreta(self):
        n = Nomenclatura.objects.get(direccion=self.direccion, clase="dictamen_baja")
        self.assertEqual(n.formatear(7, 2026), "DIB-STI-TM007-26")
        self.assertEqual(n.interpretar("DIB-STI-TM007-26"), (7, 2026))
        n.plantilla = "X-{n}-{anio2}"
        n.full_clean(exclude=["direccion"])


class EmitirTests(SoporteBase):
    def test_baja_genera_folio_pasa_el_bien_a_baja_y_deja_bitacora(self):
        documento, dictamen = self.baja()
        self.assertEqual(documento.folio, f"DIB-STI-TM001-{documento.fecha:%y}")
        self.assertEqual(documento.clase, "dictamen_baja")
        self.assertEqual(dictamen.equipos.count(), 1)
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "baja")
        entrada = self.laptop.historial.filter(accion=HistorialBien.Accion.DICTAMEN).get()
        self.assertEqual(entrada.datos["folio"], documento.folio)
        self.assertEqual(entrada.datos["cambios"]["estado"]["despues"], "baja")

    def test_baja_rechaza_bien_ya_dado_de_baja_o_prestado_o_repetido(self):
        self.baja()
        with self.assertRaises(ValidationError):
            self.baja()
        otro = Bien.objects.create(direccion=self.direccion, nombre="PC")
        with self.assertRaises(ValidationError):
            self.baja([{"equipo": "PC", "bien": otro}, {"equipo": "PC", "bien": otro}])

    def test_baja_requiere_clasificacion_y_disposicion(self):
        with self.assertRaises(ValidationError):
            svc.emitir_baja(
                usuario=self.user, direccion=self.direccion, contraparte="X", ticket="", equipos=[{"equipo": "PC"}],
                datos={"clasificacion": "no", "disposicion": "destruccion"}, elaboro_nombre="T", elaboro_cargo="T",
                autoriza_nombre="J", autoriza_cargo="D",
            )
        self.assertFalse(Documento.objects.filter(clase="dictamen_baja").exists())

    def test_baja_de_equipo_fuera_del_catalogo_no_toca_bienes(self):
        documento, dictamen = self.baja([{"equipo": "Monitor ajeno", "serie": "M-9", "departamento": "Obras"}])
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "disponible")
        self.assertEqual(dictamen.equipos.get().departamento, "Obras")

    def test_alta_solo_documenta_y_no_crea_bienes(self):
        antes = Bien.objects.count()
        documento, _ = svc.emitir_alta(
            usuario=self.user, direccion=self.direccion, contraparte="Obras", ticket="55",
            datos={"solicitud": "Equipo nuevo", "justificacion": "Se entregó", "dictamen": "Procede"},
            elaboro_nombre="T", elaboro_cargo="T", autoriza_nombre="J", autoriza_cargo="D",
        )
        self.assertEqual((documento.clase, Bien.objects.count()), ("dictamen_alta", antes))
        with self.assertRaises(ValidationError):
            svc.emitir_alta(usuario=self.user, direccion=self.direccion, contraparte="Obras", ticket="", datos={"solicitud": "x"},
                            elaboro_nombre="T", elaboro_cargo="T", autoriza_nombre="J", autoriza_cargo="D")

    def test_diagnostico_registra_en_la_bitacora_del_bien(self):
        documento, _ = svc.emitir_diagnostico(
            usuario=self.user, direccion=self.direccion, solicitante="Ana", ticket="9",
            equipo={"equipo": "Laptop", "bien": self.laptop},
            datos={"fallo": "No enciende", "causa": "Fuente", "solucion": "Cambiar", "recomendacion": "mantenimiento"},
            elaboro_nombre="T", elaboro_cargo="T",
        )
        self.assertTrue(documento.folio.startswith("DT-STI-TM001-"))
        self.assertEqual(self.laptop.historial.filter(accion="diagnostico").count(), 1)

    def test_sin_soporte_habilitado_no_se_emite(self):
        Direccion.objects.filter(pk=self.direccion.pk).update(soporte_habilitado=False)
        self.direccion.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.baja()


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VistasDeSoporteTests(SoporteBase):
    def test_lista_y_formularios_responden_y_estan_en_su_area(self):
        pagina = self.client.get(reverse("seguimientos_oficios:soporte"))
        self.assertEqual(pagina.status_code, 200)
        self.assertEqual(pagina.context["area_actual"]["clave"], "soporte")
        for nombre in ("soporte_crear_diagnostico", "soporte_crear_baja", "soporte_crear_alta"):
            self.assertEqual(self.client.get(reverse(f"seguimientos_oficios:{nombre}")).status_code, 200, nombre)

    def test_crear_baja_por_post_e_imprimir(self):
        r = self.client.post(reverse("seguimientos_oficios:soporte_crear_baja"), {
            "direccion": self.direccion.pk, "ticket": "77", "elaboro_cargo": "Técnico", "contraparte": "Tesorería",
            "solicitante": "Ana", "diagnostico": "Dañada", "clasificacion": "no_reparable", "disposicion": "destruccion",
            "autoriza_nombre": "Jefe", "autoriza_cargo": "Director",
            "eq-0-bien": str(self.laptop.pk), "eq-0-equipo": "", "eq-0-departamento": "Innovación",
        })
        dictamen = Dictamen.objects.get()
        self.assertRedirects(r, reverse("seguimientos_oficios:documento_detail", args=[dictamen.documento_id]))
        self.assertEqual(dictamen.equipos.get().serie, "LT-1")
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "baja")
        impreso = self.client.get(reverse("seguimientos_oficios:soporte_imprimir", args=[dictamen.documento_id]))
        self.assertContains(impreso, dictamen.documento.folio)
        self.assertContains(impreso, "DICTAMINA SU NO UTILIDAD")
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[dictamen.documento_id]))
        self.assertEqual(detalle.context["area_actual"]["clave"], "soporte")

    def test_diagnostico_e_impresion_de_alta(self):
        self.client.post(reverse("seguimientos_oficios:soporte_crear_diagnostico"), {
            "direccion": self.direccion.pk, "elaboro_cargo": "Técnico", "solicitante": "Ana", "fecha_recibido": "2026-07-21",
            "fallo": "f", "causa": "c", "solucion": "s", "recomendacion": "baja", "eq-0-equipo": "PC", "eq-0-serie": "S1",
        })
        diag = Dictamen.objects.get()
        self.assertContains(self.client.get(reverse("seguimientos_oficios:soporte_imprimir", args=[diag.documento_id])), "21/07/2026")
        alta, _ = svc.emitir_alta(
            usuario=self.user, direccion=self.direccion, contraparte="Obras", ticket="5",
            datos={"solicitud": "S", "justificacion": "J", "dictamen": "D"}, elaboro_nombre="T", elaboro_cargo="T",
            autoriza_nombre="J", autoriza_cargo="D",
        )
        self.assertContains(self.client.get(reverse("seguimientos_oficios:soporte_imprimir", args=[alta.pk])), "A quien corresponda")

    def test_sin_permiso_de_soporte_no_entra(self):
        UserAppRole.objects.filter(user=self.user).update(role="viewer", permissions_list=P.ROLE_MAPPING["viewer"])
        for nombre in ("soporte", "soporte_crear_baja"):
            self.assertIn(self.client.get(reverse(f"seguimientos_oficios:{nombre}")).status_code, (302, 403), nombre)


class EdicionDeDictamenesTests(SoporteBase):
    def cambios(self, documento):
        return documento.historial.filter(accion="editado").order_by("created_at").last().datos

    def test_corregir_la_serie_de_un_equipo_deja_historial_y_no_toca_el_bien(self):
        documento, dictamen = self.baja()
        renglon = dictamen.equipos.get()
        svc.editar_dictamen(dictamen, usuario=self.user, campos={"ticket": "1234"}, datos={}, equipos={
            str(renglon.pk): {"equipo": "Laptop", "serie": "LT-01", "marca_modelo": "", "folio_inventario": "", "departamento": ""},
        })
        renglon.refresh_from_db()
        self.assertEqual(renglon.serie, "LT-01")
        datos = self.cambios(documento)
        self.assertEqual(datos["cambios"]["Equipo 1: serie"], {"antes": "LT-1", "despues": "LT-01"})
        documento.refresh_from_db()
        self.assertEqual(documento.folio, f"DIB-STI-TM001-{documento.fecha:%y}")
        self.laptop.refresh_from_db()
        self.assertEqual((self.laptop.estado, self.laptop.identificador), ("baja", "LT-1"))

    def test_sin_cambios_o_con_renglones_distintos_se_rechaza(self):
        documento, dictamen = self.baja()
        renglon = dictamen.equipos.get()
        igual = {str(renglon.pk): {"equipo": "Laptop", "serie": "LT-1", "marca_modelo": "", "folio_inventario": "", "departamento": ""}}
        with self.assertRaises(ValidationError):
            svc.editar_dictamen(dictamen, usuario=self.user, campos={}, datos={}, equipos=igual)
        with self.assertRaises(ValidationError):
            svc.editar_dictamen(dictamen, usuario=self.user, campos={"ticket": "9"}, datos={}, equipos={**igual, "otro": {"equipo": "X"}})

    def test_ya_firmado_exige_motivo_y_cancelado_no_se_edita(self):
        documento, dictamen = self.baja()
        renglon = dictamen.equipos.get()
        fila = {str(renglon.pk): {"equipo": "Laptop", "serie": "NUEVA", "marca_modelo": "", "folio_inventario": "", "departamento": ""}}
        Documento.objects.filter(pk=documento.pk).update(estado="entregado")
        with self.assertRaises(ValidationError):
            svc.editar_dictamen(dictamen, usuario=self.user, campos={}, datos={}, equipos=fila)
        svc.editar_dictamen(dictamen, usuario=self.user, campos={}, datos={}, equipos=fila, motivo="Error de captura de la serie")
        self.assertEqual(self.cambios(documento)["motivo"], "Error de captura de la serie")
        Documento.objects.filter(pk=documento.pk).update(estado="cancelado")
        with self.assertRaises(ValidationError):
            svc.editar_dictamen(dictamen, usuario=self.user, campos={"ticket": "1"}, datos={}, equipos=fila, motivo="Motivo suficiente")

    def test_corregir_alta_actualiza_asunto_y_busqueda(self):
        documento, dictamen = svc.emitir_alta(
            usuario=self.user, direccion=self.direccion, contraparte="Obras", ticket="5",
            datos={"solicitud": "S", "justificacion": "J", "dictamen": "D"}, elaboro_nombre="T", elaboro_cargo="T",
            autoriza_nombre="J", autoriza_cargo="D",
        )
        svc.editar_dictamen(dictamen, usuario=self.user, campos={"ticket": "77"}, datos={"solicitud": "Nueva solicitud", "justificacion": "J", "dictamen": "D"},
                            equipos={}, contraparte="Tesorería")
        documento.refresh_from_db()
        dictamen.refresh_from_db()
        self.assertEqual((dictamen.ticket, dictamen.datos["solicitud"], documento.contraparte), ("77", "Nueva solicitud", "Tesorería"))
        self.assertIn("tesoreria", documento.busqueda)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VistaEditarDictamenTests(SoporteBase):
    def test_formulario_y_guardado_de_una_baja(self):
        documento, dictamen = self.baja()
        renglon = dictamen.equipos.get()
        url = reverse("seguimientos_oficios:soporte_editar", args=[documento.pk])
        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Motivo de la corrección")
        r = self.client.post(url, {
            "direccion": self.direccion.pk, "ticket": "1234", "elaboro_cargo": "Técnico", "contraparte": "Tesorería",
            "solicitante": "Ana", "diagnostico": "No enciende", "clasificacion": "no_reparable", "disposicion": "destruccion",
            "autoriza_nombre": "Jefe", "autoriza_cargo": "Director", "motivo": "",
            "eq-0-id": str(renglon.pk), "eq-0-equipo": "Laptop", "eq-0-serie": "LT-OK", "eq-0-departamento": "Innovación",
        })
        self.assertRedirects(r, reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        renglon.refresh_from_db()
        self.assertEqual((renglon.serie, renglon.departamento), ("LT-OK", "Innovación"))
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertContains(detalle, "Corregir")
        self.assertContains(detalle, "LT-OK")

    def test_sin_permiso_de_gestion_no_edita(self):
        documento, _ = self.baja()
        UserAppRole.objects.filter(user=self.user).update(role="viewer", permissions_list=P.ROLE_MAPPING["viewer"])
        self.assertIn(self.client.get(reverse("seguimientos_oficios:soporte_editar", args=[documento.pk])).status_code, (302, 403))


class RegistroManualPorPermisoTests(SoporteBase):
    def clases(self):
        pagina = self.client.get(reverse("seguimientos_oficios:documento_create"))
        return [v for v, _ in pagina.context["form"].fields["clase"].choices]

    def test_solo_quien_gestiona_soporte_puede_registrar_diagnosticos_y_dictamenes(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.assertIn("dictamen_baja", self.clases())
        UserAppRole.objects.filter(user=self.user).update(role="editor", permissions_list=SOLO_OFICIOS)
        clases = self.clases()
        self.assertIn("oficio", clases)
        for reservada in ("diagnostico_tecnico", "dictamen_alta", "dictamen_baja", "resguardo"):
            self.assertNotIn(reservada, clases)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class GestorEnSoporteTests(SoporteBase):
    def test_los_tres_documentos_aceptan_gestor_y_aparece_en_sus_pendientes(self):
        gestor = self.gestor("Juan Gestor")
        documento, _ = self.baja(gestor=gestor)
        alta, _ = svc.emitir_alta(
            usuario=self.user, direccion=self.direccion, contraparte="Obras", ticket="", gestor=gestor,
            datos={"solicitud": "S", "justificacion": "J", "dictamen": "D"}, elaboro_nombre="T", elaboro_cargo="T",
            autoriza_nombre="J", autoriza_cargo="D",
        )
        diag, _ = svc.emitir_diagnostico(
            usuario=self.user, direccion=self.direccion, solicitante="Ana", ticket="", equipo={"equipo": "PC"}, gestor=gestor,
            datos={"fallo": "f", "causa": "c", "solucion": "s", "recomendacion": "baja"}, elaboro_nombre="T", elaboro_cargo="T",
        )
        self.assertEqual({d.gestor_id for d in (documento, alta, diag)}, {gestor.pk})

    def test_formulario_ofrece_el_gestor_y_lo_guarda(self):
        gestor = self.gestor("Maria Gestora")
        pagina = self.client.get(reverse("seguimientos_oficios:soporte_crear_alta"))
        self.assertContains(pagina, "Gestor (quien lo lleva")
        self.assertContains(pagina, "Maria Gestora")
        self.client.post(reverse("seguimientos_oficios:soporte_crear_alta"), {
            "direccion": self.direccion.pk, "ticket": "1", "elaboro_cargo": "T", "contraparte": "Obras", "gestor": gestor.pk,
            "solicitud": "S", "justificacion": "J", "dictamen": "D", "autoriza_nombre": "J", "autoriza_cargo": "D",
        })
        self.assertEqual(Dictamen.objects.get().documento.gestor, gestor)

    def test_gestor_de_otra_direccion_se_rechaza_y_se_puede_reasignar_al_corregir(self):
        otra = Direccion.objects.create(nombre="Egresos", soporte_habilitado=True)
        ajeno = self.gestor("Ajeno Gestor", otra)
        with self.assertRaises(ValidationError):
            self.baja(gestor=ajeno)
        documento, dictamen = self.baja()
        nuevo = self.gestor("Nuevo Gestor")
        renglon = dictamen.equipos.get()
        svc.editar_dictamen(dictamen, usuario=self.user, campos={}, datos={}, gestor=nuevo, equipos={
            str(renglon.pk): {"equipo": "Laptop", "serie": "LT-1", "marca_modelo": "", "folio_inventario": "", "departamento": ""},
        })
        documento.refresh_from_db()
        self.assertEqual(documento.gestor, nuevo)
        self.assertEqual(documento.historial.filter(accion="editado").order_by("created_at").last().datos["cambios"]["Gestor"], {"antes": "", "despues": "Nuevo Gestor"})


def componentes(**por_tipo):
    """Los cuatro renglones del resguardo; `por_tipo` da los datos de los que sí se entregan."""
    return [
        {"tipo": t, "equipo": n, "serie": "", "marca_modelo": "", "folio_inventario": "", "departamento": "", "info_tecnica": "",
         **por_tipo.get(t, {})}
        for t, n in svc.COMPONENTES
    ]


class ResguardoTests(SoporteBase):
    def resguardo(self, equipos=None, **extra):
        return svc.emitir_resguardo(
            usuario=self.user, direccion=self.direccion, contraparte="Tesorería", ticket="", fecha=datetime.date(2026, 7, 21),
            datos={"empleado": "Ana Pérez", "fecha_entrega": "2026-07-21"},
            equipos=equipos or componentes(equipo={"serie": "PC-1", "marca_modelo": "Dell 3020", "info_tecnica": "i5, 16 GB"},
                                           monitor={"serie": "MON-1"}),
            elaboro_nombre="Técnico", elaboro_cargo="Técnico de Soporte en TI", autoriza_nombre="Jefe", autoriza_cargo="Director", **extra,
        )

    def test_emite_con_folio_cuatro_renglones_y_fecha_de_entrega(self):
        documento, dictamen = self.resguardo()
        self.assertEqual((documento.clase, documento.fecha), ("resguardo", datetime.date(2026, 7, 21)))
        self.assertTrue(documento.folio.startswith("RES-STI-TM001-"))
        self.assertEqual([e.tipo for e in dictamen.equipos.all()], ["equipo", "monitor", "teclado", "raton"])
        self.assertEqual(dictamen.equipos.get(tipo="equipo").info_tecnica, "i5, 16 GB")
        self.assertIn("Ana Pérez", documento.asunto)

    def test_los_componentes_del_catalogo_dejan_bitacora_sin_cambiar_su_estado(self):
        self.resguardo(componentes(equipo={"bien": self.laptop, "serie": "LT-1"}))
        entrada = self.laptop.historial.get(accion="resguardo")
        self.assertEqual((entrada.datos["empleado"], entrada.datos["departamento"], entrada.datos["componente"]), ("Ana Pérez", "Tesorería", "Equipo"))
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.estado, "disponible")

    def test_validaciones(self):
        with self.assertRaises(ValidationError):
            self.resguardo(componentes())  # sin serie ni marca del equipo
        with self.assertRaises(ValidationError):
            self.resguardo(componentes(equipo={"serie": "X"})[:3])  # faltan componentes
        with self.assertRaises(ValidationError):
            svc.emitir_resguardo(
                usuario=self.user, direccion=self.direccion, contraparte="T", ticket="", fecha=datetime.date(2026, 7, 21),
                datos={"empleado": " "}, equipos=componentes(equipo={"serie": "X"}), elaboro_nombre="T", elaboro_cargo="T",
                autoriza_nombre="J", autoriza_cargo="D",
            )
        self.laptop.estado = "baja"
        self.laptop.save()
        with self.assertRaises(ValidationError):
            self.resguardo(componentes(equipo={"bien": self.laptop, "serie": "LT-1"}))

    def test_corregir_serie_y_fecha_de_entrega(self):
        documento, dictamen = self.resguardo()
        filas = {str(e.pk): {"equipo": e.equipo, "serie": e.serie, "marca_modelo": e.marca_modelo, "folio_inventario": "", "departamento": "",
                             "info_tecnica": e.info_tecnica} for e in dictamen.equipos.all()}
        pc = str(dictamen.equipos.get(tipo="equipo").pk)
        filas[pc]["serie"] = "PC-OK"
        svc.editar_dictamen(dictamen, usuario=self.user, campos={}, equipos=filas,
                            datos={"empleado": "Ana Pérez", "fecha_entrega": "2026-07-22"}, contraparte="Tesorería")
        documento.refresh_from_db()
        self.assertEqual(documento.fecha, datetime.date(2026, 7, 22))
        self.assertEqual(dictamen.equipos.get(tipo="equipo").serie, "PC-OK")
        with self.assertRaises(ValidationError):
            svc.editar_dictamen(dictamen, usuario=self.user, campos={}, equipos=filas, contraparte="Tesorería",
                                datos={"empleado": "Ana Pérez", "fecha_entrega": "2025-12-31"})


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VistaResguardoTests(SoporteBase):
    def test_formulario_creacion_e_impresion(self):
        url = reverse("seguimientos_oficios:soporte_crear_resguardo")
        pagina = self.client.get(url)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Empleado a quien se le asigna el equipo")
        self.assertContains(pagina, "Nuevo resguardo")  # menú lateral
        r = self.client.post(url, {
            "direccion": self.direccion.pk, "elaboro_cargo": "Técnico", "contraparte": "Tesorería", "fecha_entrega": "2026-07-21",
            "empleado": "Ana Pérez", "autoriza_nombre": "Jefe", "autoriza_cargo": "Director", "ticket": "",
            "eq-0-serie": "PC-1", "eq-0-marca_modelo": "Dell", "eq-0-info_tecnica": "i5", "eq-1-serie": "MON-1",
            "eq-0-bien": str(self.laptop.pk),
        })
        dictamen = Dictamen.objects.get()
        self.assertRedirects(r, reverse("seguimientos_oficios:documento_detail", args=[dictamen.documento_id]))
        impreso = self.client.get(reverse("seguimientos_oficios:soporte_imprimir", args=[dictamen.documento_id]))
        for texto in ("Resguardo de equipos de cómputo", "Ana Pérez", "PC-1", "Información del monitor", "Anexo fotográfico", "21/07/2026"):
            self.assertContains(impreso, texto)
        self.assertEqual(self.laptop.historial.filter(accion="resguardo").count(), 1)
        edicion = self.client.get(reverse("seguimientos_oficios:soporte_editar", args=[dictamen.documento_id]))
        self.assertEqual(edicion.status_code, 200)

    def test_sin_empleado_no_emite_y_conserva_lo_capturado(self):
        r = self.client.post(reverse("seguimientos_oficios:soporte_crear_resguardo"), {
            "direccion": self.direccion.pk, "elaboro_cargo": "T", "contraparte": "Tesorería", "fecha_entrega": "2026-07-21",
            "autoriza_nombre": "J", "autoriza_cargo": "D", "eq-0-serie": "PC-9",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Dictamen.objects.exists())
        self.assertContains(r, "PC-9")
