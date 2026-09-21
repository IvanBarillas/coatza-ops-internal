from importlib import import_module

from django.apps import apps
from django.apps import AppConfig


class SharedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shared"

    def ready(self):
        """Descubre automáticamente módulos ``workflows`` de las apps."""
        from . import checks  # noqa: F401  (registra las comprobaciones de arranque)

        for app_config in apps.get_app_configs():
            module_name = f"{app_config.name}.workflows"
            try:
                import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name != module_name:
                    raise
