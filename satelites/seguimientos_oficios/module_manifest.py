from .integracion import ModuleManifest

MODULE_MANIFEST = ModuleManifest(
    code="seguimientos_oficios",
    name="Seguimiento de Oficios",
    description="Registro, consulta y trazabilidad de oficios recibidos y enviados.",
    entry_url="seguimientos_oficios:documento_list",
    urlconf="satelites.seguimientos_oficios.urls",
    url_prefix="app/seguimientos-oficios/",
    icon="file-text",
    dependencies=("security", "accounts", "organigrama"),
    default_enabled=False,
    can_disable=True,
)
