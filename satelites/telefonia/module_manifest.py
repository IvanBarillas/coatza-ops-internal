from .integracion import ModuleManifest

MODULE_MANIFEST = ModuleManifest(
    code="telefonia",
    name="Telefonía y enlaces",
    description="Líneas y enlaces del municipio, con su ubicación en el mapa, y el seguimiento de los reportes de falla a Telmex.",
    entry_url="telefonia:inicio",
    urlconf="satelites.telefonia.urls",
    url_prefix="app/telefonia/",
    icon="phone-call",
    dependencies=("security", "accounts", "organigrama"),
    default_enabled=False,
    can_disable=True,
)
