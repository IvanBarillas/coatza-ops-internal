import datetime
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.security.models import AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.permisos_personal.models import Configuracion, Empleado, RangoAntiguedad, Tipo
from satelites.permisos_personal.permissions import PermisosPersonalPermissions as P

# 2026: el 2 de marzo es lunes; el 4 de julio es sábado.
LUNES = datetime.date(2026, 3, 2)


def d(mes, dia, anio=2026):
    return datetime.date(anio, mes, dia)


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False, AXENTRA_CORE_VERBOSE_RADAR=False)
class BasePermisos(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app, _ = AppModule.objects.get_or_create(slug=P.APP_CODE, defaults={"name": "Permisos"})
        cls.app.is_active = True
        cls.app.save()
        dep = Dependencia.objects.create(nombre="Innovación")
        cls.sede_a = Sede.objects.create(nombre="Palacio")
        cls.sede_b = Sede.objects.create(nombre="Tesorería")
        cls.area = AreaOperativa.objects.create(nombre="Soporte", dependencia=dep, sede_fisica=cls.sede_a)
        Configuracion.objects.update_or_create(pk=1, defaults={"dias_economicos_p1": 1, "dias_economicos_p2": 2})
        for tipo, desde, p1, p2 in (("sindicalizado", 0, 6, 6), ("sindicalizado", 5, 10, 8), ("confianza", 0, 5, 5), ("confianza", 3, 7, 4)):
            RangoAntiguedad.objects.create(tipo=tipo, desde_anios=desde, dias_p1=p1, dias_p2=p2)
        cls.control = cls.usuario("control@example.test", "control", "Carla", "Control")
        cls.ana = cls.empleado("ana@example.test", "empleado", "Ana", "Sindicalizada", Tipo.SINDICALIZADO, d(1, 15, 2019), cls.sede_a)
        cls.beto = cls.empleado("beto@example.test", "empleado", "Beto", "Confianza", Tipo.CONFIANZA, d(6, 1, 2024), cls.sede_a)
        cls.cris = cls.empleado("cris@example.test", "empleado", "Cris", "Sindicalizado", Tipo.SINDICALIZADO, d(2, 1, 2025), cls.sede_b)

    @classmethod
    def usuario(cls, correo, rol, nombre, apellido):
        u = get_user_model().objects.create_user(email=correo, first_name=nombre, last_name=apellido)
        UserProfile.objects.create(user=u, area=cls.area)
        UserAppRole.objects.create(user=u, app=cls.app, role=rol, permissions_list=P.ROLE_MAPPING[rol])
        return u

    @classmethod
    def empleado(cls, correo, rol, nombre, apellido, tipo, ingreso, sede):
        u = cls.usuario(correo, rol, nombre, apellido)
        return Empleado.objects.create(usuario=u, tipo=tipo, fecha_ingreso=ingreso, sede_uuid=sede.pk, sede_nombre=sede.nombre)
