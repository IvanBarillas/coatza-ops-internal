from django.apps import AppConfig


class EventosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "satelites.eventos"
    label = "eventos"
    verbose_name = "Eventos"

    def ready(self):
        from .integracion import registrar_proveedor
        from .proveedores import ProveedorVinculos

        registrar_proveedor(ProveedorVinculos.NOMBRE, ProveedorVinculos())
