from .integracion import ModuleManifest

MODULE_MANIFEST = ModuleManifest(
    code="eventos",
    name="Eventos",
    description="Eventos que Innovación cubre: técnicos por tramo de horas, vales de salida, trámites de telefonía, calendario y bitácora.",
    entry_url="eventos:inicio",
    urlconf="satelites.eventos.urls",
    url_prefix="app/eventos/",
    icon="calendar-clock",
    dependencies=("security", "accounts", "organigrama"),
    optional_integrations=("prestamos.vales",),
    default_enabled=False,
    can_disable=True,
)
