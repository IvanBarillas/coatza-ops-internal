"""API pública y neutral del SDK modular de Axentra OS."""

from .catalog import ModuleCatalogEntry, available_module_catalog
from .contracts import (
    ModuleHealth,
    ModuleKind,
    ModuleManifest,
    ModuleRuntimeStatus,
    PublicEntry,
    PublicSurface,
)
from .registry import module_registry, register_module

__all__ = [
    "ModuleHealth",
    "ModuleKind",
    "ModuleManifest",
    "ModuleRuntimeStatus",
    "PublicEntry",
    "PublicSurface",
    "ModuleCatalogEntry",
    "available_module_catalog",
    "module_registry",
    "register_module",
]
