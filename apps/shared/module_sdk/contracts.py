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


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    code: str
    name: str
    description: str
    entry_url: str
    # URL pública (texto plano) para el directorio del ciudadano. Nunca se
    # resuelve con reverse(): puede vivir en otro dominio. Vacío = no aparece.
    entry_url_publico: str = ""
    urlconf: str = ""
    url_prefix: str = ""
    version: str = "1.0.0"
    icon: str = "blocks"
    kind: ModuleKind = ModuleKind.SATELLITE
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    optional_integrations: tuple[str, ...] = field(default_factory=tuple)
    default_enabled: bool = False
    can_disable: bool = True

    def __post_init__(self):
        code = str(self.code).strip().lower()
        if not code or not code.replace("_", "").replace("-", "").isalnum():
            raise ValueError("El módulo requiere un código técnico válido.")
        if code in self.dependencies:
            raise ValueError("Un módulo no puede depender de sí mismo.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "entry_url_publico", str(self.entry_url_publico).strip())
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
]
