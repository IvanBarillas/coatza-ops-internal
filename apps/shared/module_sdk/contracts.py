from dataclasses import dataclass, field
from enum import StrEnum


class ModuleKind(StrEnum):
    CORE = "CORE"
    SATELLITE = "SATELLITE"


class ModuleHealth(StrEnum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"


def _normalize_prefix(prefix):
    """Prefijo de URL sin "/" inicial y con "/" final; vacío se queda vacío."""
    prefix = str(prefix).strip().strip("/")
    return f"{prefix}/" if prefix else ""


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    code: str
    name: str
    description: str
    entry_url: str
    # URL pública (texto plano) para el directorio del ciudadano. Nunca se
    # resuelve con reverse(): puede vivir en otro dominio. Vacío = no aparece.
    entry_url_publico: str = ""
    # Texto para el ciudadano en el directorio público; vacío = usa description
    # (que suele estar redactada para el personal).
    descripcion_publica: str = ""
    urlconf: str = ""
    url_prefix: str = ""
    version: str = "1.0.0"
    icon: str = "blocks"
    kind: ModuleKind = ModuleKind.SATELLITE
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    optional_integrations: tuple[str, ...] = field(default_factory=tuple)
    default_enabled: bool = False
    can_disable: bool = True
    # API servicio-a-servicio (django-ninja, autenticada con INTERNAL_API_KEY)
    # que el satélite publica en la raíz de la instalación, junto al Hub. El
    # Core la monta en ``satellite_urlpatterns()``; sin ``api_urlconf`` no se
    # monta nada. Prefijo sin "/" inicial y con "/" final (se normaliza).
    api_urlconf: str = ""
    api_prefix: str = "api/v1/"
    # Vistas públicas (sin login) del satélite, en la superficie ciudadana de la
    # instalación: el Core las monta bajo ``public_prefix`` en el urlconf que
    # sirve el dominio del ciudadano (``core.urls_publico``). Un solo dominio
    # ciudadano = una sola cookie de sesión para todos los satélites públicos.
    # Distinto de ``urlconf`` (panel de personal): pueden compartir app_name
    # porque nunca se montan en el mismo urlconf.
    public_urlconf: str = ""
    public_prefix: str = ""

    def __post_init__(self):
        code = str(self.code).strip().lower()
        if not code or not code.replace("_", "").replace("-", "").isalnum():
            raise ValueError("El módulo requiere un código técnico válido.")
        if code in self.dependencies:
            raise ValueError("Un módulo no puede depender de sí mismo.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "api_urlconf", str(self.api_urlconf).strip())
        object.__setattr__(self, "api_prefix", _normalize_prefix(self.api_prefix))
        if self.api_urlconf and not self.api_prefix:
            raise ValueError("api_urlconf requiere un api_prefix no vacío.")
        object.__setattr__(self, "public_urlconf", str(self.public_urlconf).strip())
        object.__setattr__(self, "public_prefix", _normalize_prefix(self.public_prefix))
        if self.public_urlconf and not self.public_prefix:
            raise ValueError("public_urlconf requiere un public_prefix no vacío.")
        object.__setattr__(self, "entry_url_publico", str(self.entry_url_publico).strip())
        object.__setattr__(self, "descripcion_publica", str(self.descripcion_publica).strip())
        object.__setattr__(
            self,
            "dependencies",
            tuple(str(item).strip().lower() for item in self.dependencies),
        )
        object.__setattr__(
            self,
            "optional_integrations",
            tuple(str(item).strip().lower() for item in self.optional_integrations),
        )


@dataclass(frozen=True, slots=True)
class PublicEntry:
    """Entrada del directorio público de quien NO es un módulo del Hub.

    Para paquetes sin panel de personal (p. ej. Ciudadanía): no genera
    ``AppModule`` ni tarjeta en el Hub. ``url`` es texto plano, nunca pasa
    por ``reverse()``. Se publica desde ``<app>.public_entry.get_public_entry``.
    """

    code: str
    name: str
    description: str
    url: str
    icon: str = "blocks"

    def __post_init__(self):
        code = str(self.code).strip().lower()
        if not code or not code.replace("_", "").replace("-", "").isalnum():
            raise ValueError("La entrada pública requiere un código técnico válido.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "url", str(self.url).strip())
        object.__setattr__(self, "description", str(self.description).strip())


@dataclass(frozen=True, slots=True)
class PublicSurface:
    """Vistas públicas de un paquete, montadas en la superficie ciudadana.

    Un módulo con manifiesto la declara con ``public_urlconf``/``public_prefix``.
    Un paquete sin panel (Ciudadanía) publica las constantes ``PUBLIC_URLCONF`` y
    ``PUBLIC_PREFIX`` en ``<app>/public_entry.py``: son estáticas a propósito (el
    urlconf se arma una vez al arrancar; ``get_public_entry()`` se evalúa por
    petición y puede devolver ``None`` sin que las rutas deban desmontarse).
    """

    code: str
    urlconf: str
    prefix: str

    def __post_init__(self):
        object.__setattr__(self, "urlconf", str(self.urlconf).strip())
        object.__setattr__(self, "prefix", _normalize_prefix(self.prefix))
        if not self.urlconf or not self.prefix:
            raise ValueError("La superficie pública requiere urlconf y prefijo no vacíos.")


@dataclass(frozen=True, slots=True)
class ModuleRuntimeStatus:
    manifest: ModuleManifest
    installed: bool
    enabled: bool
    health: ModuleHealth
    message: str = ""
    missing_dependencies: tuple[str, ...] = field(default_factory=tuple)

    @property
    def available(self):
        return self.installed and self.enabled and self.health == ModuleHealth.HEALTHY


__all__ = [
    "ModuleHealth",
    "ModuleKind",
    "ModuleManifest",
    "ModuleRuntimeStatus",
    "PublicEntry",
    "PublicSurface",
]
