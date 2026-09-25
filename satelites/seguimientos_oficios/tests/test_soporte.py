from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Bien, Dictamen, Direccion, Documento, HistorialBien, Nomenclatura
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.soporte import services as svc

from .base import BaseAdjuntos


class SoporteBase(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        Direccion.objects.filter(pk=self.direccion.pk).update(soporte_habilitado=True)
        self.direccion.refresh_from_db()
        for clase, prefijo in (("diagnostico_tecnico", "DT"), ("dictamen_baja", "DIB"), ("dictamen_alta", "DIA")):
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
