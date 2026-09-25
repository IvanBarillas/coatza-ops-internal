import datetime
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.security.models import AppModule, AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.telefonia.models import Linea
from satelites.telefonia.permissions import TelefoniaPermissions as P

def _png_valido():
    import io

    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (2, 2), (200, 30, 30)).save(salida, "PNG")
    return salida.getvalue()


PNG = _png_valido()
HOY = datetime.date.today()


def png(nombre="foto.png", contenido=PNG):
    return SimpleUploadedFile(nombre, contenido, content_type="image/png")


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False, AXENTRA_CORE_VERBOSE_RADAR=False)
class BaseTelefonia(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.app, _ = AppModule.objects.get_or_create(slug=P.APP_CODE, defaults={"name": "Telefonía"})
        cls.app.is_active = True
        cls.app.save()
        dep = Dependencia.objects.create(nombre="Innovación")
        area = AreaOperativa.objects.create(nombre="Soporte", dependencia=dep, sede_fisica=Sede.objects.create(nombre="Palacio"))
        cls.area = area
        cls.operador = cls.usuario("operador@example.test", "operador", "Olga", "Operadora")
        cls.tecnico = cls.usuario("tecnico@example.test", "tecnico", "Tomás", "Técnico")
        cls.otro_tecnico = cls.usuario("otro@example.test", "tecnico", "Óscar", "Otro")
        cls.lector = cls.usuario("lector@example.test", "viewer", "Lucía", "Lectora")
        cls.dueno = cls.usuario("dueno@example.test", "owner", "Diego", "Dueño")
        cls.linea = Linea.objects.create(identificador="9212165053", sitio="Línea Allende", direccion="Av. Allende 1", latitud=18.15, longitud=-94.42)

    @classmethod
    def usuario(cls, correo, rol, nombre, apellido):
        u = get_user_model().objects.create_user(email=correo, first_name=nombre, last_name=apellido)
        u.phone = "9211110000"
        u.save()
        UserProfile.objects.create(user=u, area=cls.area)
        UserAppRole.objects.create(user=u, app=cls.app, role=rol, permissions_list=P.ROLE_MAPPING[rol])
        return u

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.override = override_settings(TEL_ARCHIVOS_ROOT=self._tmp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
