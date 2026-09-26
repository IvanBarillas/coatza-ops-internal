import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.security.models import AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.eventos.permissions import EventosPermissions as P


def momento(dia, hora, minuto=0, mes=9, anio=2030):
    return timezone.make_aware(datetime.datetime(anio, mes, dia, hora, minuto))


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False, AXENTRA_CORE_VERBOSE_RADAR=False)
class BaseEventos(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app, _ = AppModule.objects.get_or_create(slug=P.APP_CODE, defaults={"name": "Eventos"})
        cls.app.is_active = True
        cls.app.save()
        dep = Dependencia.objects.create(nombre="Innovación")
        sede = Sede.objects.create(nombre="Palacio")
        cls.area = AreaOperativa.objects.create(nombre="Soporte", dependencia=dep, sede_fisica=sede)
        cls.coord = cls.usuario("coord@example.test", "coordinador", "Carla", "Coordinadora")
        cls.diego = cls.usuario("diego@example.test", "tecnico", "Diego", "Técnico")
        cls.vale = cls.usuario("vale@example.test", "tecnico", "Valeria", "Técnica")
        cls.lector = cls.usuario("lector@example.test", "viewer", "Lola", "Lectora")

    @classmethod
    def usuario(cls, correo, rol, nombre, apellido):
        u = get_user_model().objects.create_user(email=correo, first_name=nombre, last_name=apellido)
        UserProfile.objects.create(user=u, area=cls.area)
        UserAppRole.objects.create(user=u, app=cls.app, role=rol, permissions_list=P.ROLE_MAPPING[rol])
        return u

    def evento(self, nombre="Feria", inicio=None, fin=None, **extra):
        from satelites.eventos import services
        return services.crear_evento(
            usuario=self.coord, nombre=nombre, lugar="Malecón", inicio=inicio or momento(10, 9), fin=fin or momento(10, 22), **extra,
        )
