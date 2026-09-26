from django.apps import AppConfig


class TelefoniaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "satelites.telefonia"
    label = "telefonia"
    verbose_name = "Telefonía y enlaces"

    def ready(self):
        from .integracion import registrar_proveedor
        from .proveedores import ProveedorLineas

        registrar_proveedor(ProveedorLineas.NOMBRE, ProveedorLineas())
