# apps/security/models/infrastructure.py

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.shared.branding import DEFAULT_BRAND_COLORS
from apps.shared.models import AxentraBaseModel

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="El color debe ser un valor hexadecimal válido, por ejemplo #0B1A15.",
)


class AppModule(AxentraBaseModel):
    """Inventario de módulos federados en el Core OS."""

    name = models.CharField("Nombre del Módulo", max_length=100)
    slug = models.SlugField("Identificador Técnico", unique=True)
    description = models.TextField("Descripción Operativa", blank=True)
    version = models.CharField("Versión instalada", max_length=40, default="1.0.0")
    icon = models.CharField("Icono", max_length=80, default="blocks")
    entry_url_name = models.CharField("Ruta de entrada", max_length=160, blank=True)
    module_kind = models.CharField(
        "Tipo de módulo",
        max_length=20,
        choices=(("CORE", "Núcleo"), ("SATELLITE", "Satélite")),
        default="SATELLITE",
    )
    dependencies = models.JSONField("Dependencias obligatorias", default=list, blank=True)
    optional_integrations = models.JSONField("Integraciones opcionales", default=list, blank=True)
    health_status = models.CharField(
        "Estado de salud",
        max_length=20,
        choices=(
            ("HEALTHY", "Saludable"),
            ("WARNING", "Con advertencias"),
            ("UNAVAILABLE", "No disponible"),
            ("DISABLED", "Deshabilitado"),
        ),
        default="HEALTHY",
    )
    health_message = models.CharField("Detalle de salud", max_length=255, blank=True)
    last_health_check_at = models.DateTimeField("Última comprobación", null=True, blank=True)

    class Meta:
        db_table = "axentra_sec_modules"
        verbose_name = "Módulo Instalado"
        verbose_name_plural = "Módulos Instalados"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserAppRole(AxentraBaseModel):
    """Matriz dinámica de membresías por app con roles declarados por manifiesto."""

    class ReservedRoles(models.TextChoices):
        OWNER = "owner", "👑 Dueño / Director General"
        ADMIN = "admin", "🔒 Administrador"
        EDITOR = "editor", "📝 Editor / Operador"
        REVIEWER = "reviewer", "👁️ Revisor / Auditor"
        VIEWER = "viewer", "👤 Solo Lectura"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name="Funcionario Público",
    )

    app = models.ForeignKey(
        AppModule,
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name="Módulo Autorizado",
    )

    role = models.CharField(
        "Rol Funcional en el Módulo",
        max_length=50,
        default=ReservedRoles.VIEWER,
        db_index=True,
        help_text="Rol declarado en el permissions.py del módulo. Ej: owner, admin, director_rh, sma_manager.",
    )

    permissions_list = models.JSONField(
        "Lista de Permisos Finos",
        default=list,
        blank=True,
        help_text="Snapshot de permisos finos derivados del rol funcional.",
    )

    class Meta:
        db_table = "axentra_sec_user_roles"
        verbose_name = "Permiso de Aplicación"
        verbose_name_plural = "Permisos de Aplicaciones"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "app"],
                name="uq_user_app_role",
            )
        ]

    def __str__(self):
        return f"{self.user.email} ➡️ {self.app.name} ({self.role})"

    def has_fine_permission(self, permission_string: str) -> bool:
        if not self.is_active or self.is_deleted:
            return False

        if self.role == self.ReservedRoles.OWNER:
            return True

        return permission_string in (self.permissions_list or [])


class Municipality(AxentraBaseModel):
    """
    Catálogo municipal para claves oficiales INEGI / ORFIS.

    Ejemplo:
    039 · COATZACOALCOS
    """

    code = models.CharField(
        "Clave Municipal",
        max_length=3,
        unique=True,
        db_index=True,
        help_text="Clave municipal INEGI/ORFIS. Ejemplo: 039 para Coatzacoalcos.",
    )

    name = models.CharField(
        "Municipio",
        max_length=150,
        db_index=True,
    )

    state_code = models.CharField(
        "Clave del Estado",
        max_length=2,
        blank=True,
        help_text="Clave INEGI del estado. Veracruz = 30.",
    )

    state_name = models.CharField(
        "Estado",
        max_length=120,
        blank=True,
        default="VERACRUZ",
    )

    class Meta:
        db_table = "axentra_core_municipalities"
        verbose_name = "Municipio"
        verbose_name_plural = "Municipios"
        ordering = ["state_code", "code", "name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["state_code"]),
            models.Index(fields=["is_active", "is_deleted"]),
        ]

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().zfill(3)

        if self.name:
            self.name = self.name.strip().upper()

        if self.state_code:
            self.state_code = self.state_code.strip().zfill(2)

        if self.state_name:
            self.state_name = self.state_name.strip().upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} · {self.name}"


class TenantConfig(AxentraBaseModel):
    """Configuración de Marca e Identidad Legal del Ayuntamiento."""

    app_name = models.CharField(
        "Nombre del Sistema",
        max_length=50,
        default="GovStack",
    )

    entidad_nombre = models.CharField(
        "Nombre del Ayuntamiento / Institución",
        max_length=150,
        default="H. Ayuntamiento Constitucional",
    )

    siglas = models.CharField(
        "Siglas de la Entidad",
        max_length=15,
        default="GOV",
    )

    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.PROTECT,
        related_name="tenant_configs",
        verbose_name="Municipio",
        null=True,
        blank=True,
        help_text="Municipio oficial asociado a la configuración institucional.",
    )

    direccion_oficial = models.TextField(
        "Dirección Institucional Sede",
        blank=True,
    )

    rfc = models.CharField(
        "RFC de la Institución",
        max_length=13,
        blank=True,
    )

    logo_light = models.ImageField(
        "Escudo Oficial (Fondo Claro)",
        upload_to="institucion/logos/",
        blank=True,
        null=True,
    )

    logo_dark = models.ImageField(
        "Escudo Oficial (Fondo Oscuro)",
        upload_to="institucion/logos/",
        blank=True,
        null=True,
    )

    primary_color_class = models.CharField(
        "Color de Acento (Tailwind Class)",
        max_length=30,
        default="slate-950",
        help_text="Clase nativa de Tailwind para branding.",
    )

    primary_color = models.CharField(
        "Color Primario (HEX)",
        max_length=7,
        default=DEFAULT_BRAND_COLORS["primary"],
        validators=[hex_color_validator],
        help_text="Color primario de marca institucional en formato hexadecimal, ej. #0B1A15.",
    )

    secondary_color = models.CharField(
        "Color Secundario (HEX)",
        max_length=7,
        default=DEFAULT_BRAND_COLORS["secondary"],
        validators=[hex_color_validator],
        help_text="Color secundario de marca institucional en formato hexadecimal, ej. #475467.",
    )

    accent_color = models.CharField(
        "Color de Acento (HEX)",
        max_length=7,
        default=DEFAULT_BRAND_COLORS["accent"],
        validators=[hex_color_validator],
        help_text="Color de acento de marca institucional en formato hexadecimal, ej. #059669.",
    )

    enable_whatsapp_support = models.BooleanField(
        "Habilitar Soporte por WhatsApp",
        default=True,
        help_text="Activa el botón flotante de contacto por WhatsApp en la portada pública.",
    )

    whatsapp_number = models.CharField(
        "Número de WhatsApp Institucional",
        max_length=20,
        blank=True,
        help_text="Número institucional con código de país, solo dígitos. Ej. 5219211234567.",
    )

    whatsapp_default_message = models.CharField(
        "Mensaje Inicial de WhatsApp",
        max_length=255,
        default="Hola, necesito asistencia en el Portal Digital de Axentra OS.",
        blank=True,
        help_text="Mensaje precargado que el ciudadano ve al abrir la conversación de WhatsApp.",
    )

    show_whatsapp_on_public_landing = models.BooleanField(
        "Mostrar WhatsApp en Portada Pública",
        default=True,
        help_text="Controla si el botón flotante de WhatsApp aparece en la portada pública del Core.",
    )

    # Hallazgo real (ver docs/apps/public-municipal-portal.md y la
    # discusión que lo originó): cada satélite instalado por separado
    # (ej. axentra-mod-tramites, ConfigMunicipal.aviso_privacidad) venía
    # duplicando su propio texto legal — un riesgo de cumplimiento real,
    # no solo desorden: alguien actualiza el aviso en un satélite y se
    # le olvida en los demás. Vive aquí, en el tenant único de la
    # instalación, para que exista una sola fuente de verdad legal que
    # cualquier satélite pueda consultar.
    aviso_privacidad = models.TextField(
        "Aviso de Privacidad",
        blank=True,
        default="",
        help_text="Texto legal del aviso de privacidad institucional, visible en el portal público.",
    )

    politica_cookies = models.TextField(
        "Política de Cookies",
        blank=True,
        default="",
        help_text="Texto legal de la política de cookies institucional, visible en el portal público.",
    )

    class Meta:
        db_table = "axentra_core_tenant_config"
        verbose_name = "Configuración Institucional"
        verbose_name_plural = "Configuraciones Institucionales"

    def __str__(self):
        return f"Configuración Activa: {self.entidad_nombre}"

    def save(self, *args, **kwargs):
        if self.entidad_nombre:
            self.entidad_nombre = self.entidad_nombre.strip().upper()

        if self.siglas:
            self.siglas = self.siglas.strip().upper()

        if self.rfc:
            self.rfc = self.rfc.strip().upper()

        if not self.pk and TenantConfig.objects.exists():
            return TenantConfig.objects.first()

        return super().save(*args, **kwargs)
    
