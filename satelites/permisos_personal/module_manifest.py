from .integracion import ModuleManifest

MODULE_MANIFEST = ModuleManifest(
    code="permisos_personal",
    name="Permisos del personal",
    description="Solicitud y control de vacaciones y días económicos del personal, con calendario y cobertura por sede.",
    entry_url="permisos_personal:inicio",
    urlconf="satelites.permisos_personal.urls",
    url_prefix="app/permisos-personal/",
    icon="calendar-days",
    dependencies=("security", "accounts", "organigrama"),
    default_enabled=False,
    can_disable=True,
)
