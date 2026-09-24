from io import StringIO

from django.core.management import call_command

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P

from .base import BaseAdjuntos


class SincronizarPermisosTests(BaseAdjuntos):
    def correr(self, *args):
        salida = StringIO()
        call_command("oficios_sincronizar_permisos", *args, stdout=salida)
        return salida.getvalue()

    def test_agrega_lo_que_falta_sin_quitar_y_solo_aplicando(self):
        UserAppRole.objects.filter(user=self.user).update(
            role="owner", permissions_list=["has_access_module", "can_view_oficios", "permiso_personalizado"]
        )
        self.assertIn("Se actualizarían (simulación): 1", self.correr())
        self.assertNotIn("can_manage_catalogs", UserAppRole.objects.get(user=self.user).permissions_list)
        self.correr("--aplicar")
        permisos = UserAppRole.objects.get(user=self.user).permissions_list
        self.assertIn("permiso_personalizado", permisos)
        self.assertTrue(set(P.ROLE_MAPPING["owner"]) <= set(permisos))
        self.assertIn("Actualizadas: 0", self.correr("--aplicar"))

    def test_por_defecto_no_toca_otros_roles(self):
        antes = list(UserAppRole.objects.get(user=self.user).permissions_list)
        UserAppRole.objects.filter(user=self.user).update(role="editor", permissions_list=["has_access_module"])
        self.assertIn("simulación): 0", self.correr())
        self.assertIn("simulación): 1", self.correr("--rol", "editor"))
        self.assertTrue(antes)
