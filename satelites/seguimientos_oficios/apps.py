from django.apps import AppConfig


class SeguimientosOficiosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "satelites.seguimientos_oficios"
    label = "seguimientos_oficios"
    verbose_name = "Seguimiento de Oficios"

    def ready(self):
        from .integracion import registrar_proveedor
        from .proveedores import ProveedorVales

        registrar_proveedor(ProveedorVales.NOMBRE, ProveedorVales())
