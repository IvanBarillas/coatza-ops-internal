from django.core.management.base import BaseCommand

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P


class Command(BaseCommand):
    help = (
        "Agrega a las membresías del módulo los permisos que su rol tiene hoy y aún no figuran en su "
        "snapshot (p. ej. tras publicar permisos nuevos). Solo agrega; nunca quita. Sin --aplicar solo simula."
    )

    def add_arguments(self, parser):
        parser.add_argument("--rol", action="append", choices=sorted(P.ROLE_MAPPING), help="Repetible; por defecto owner.")
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **opciones):
        roles = opciones["rol"] or ["owner"]
        total = 0
        membresias = UserAppRole.objects.filter(
            app__slug=P.APP_CODE, role__in=roles, is_active=True, is_deleted=False
        ).select_related("user")
        for membresia in membresias:
            actuales = list(membresia.permissions_list or [])
            faltan = [p for p in P.ROLE_MAPPING[membresia.role] if p not in actuales]
            if not faltan:
                continue
            total += 1
            self.stdout.write(f"{membresia.user.email} ({membresia.role}): + {', '.join(faltan)}")
            if opciones["aplicar"]:
                membresia.permissions_list = actuales + faltan
                membresia.save()
        modo = "Actualizadas" if opciones["aplicar"] else "Se actualizarían (simulación)"
        self.stdout.write(f"{modo}: {total}")
