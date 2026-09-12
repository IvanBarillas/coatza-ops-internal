# apps/security/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.security.forms import CustomUserCreationForm, CustomUserChangeForm
from apps.security.models import (
    User,
    UserProfile,
    Sede,
    Dependencia,
    AreaOperativa,
    AppDependencyCapability,
    AppModule,
    UserAppRole,
    Municipality,
    TenantConfig,
    OfficialParameter,
    SecurityAuditLog,
)


# =========================================================================
# 🧬 MIXIN BASE PARA ENTIDADES AXENTRA
# =========================================================================
class AxentraBaseAdminMixin:
    """Mixin administrativo para modelos que heredan de AxentraBaseModel."""

    readonly_fields = ("id", "created_at", "updated_at")
    base_state_fields = ("is_active", "is_deleted", "deleted_at")
    base_audit_fields = ("id", "created_at", "updated_at")


# =========================================================================
# 👤 BLOQUE 1: IDENTIDAD DIGITAL Y CUENTAS
# =========================================================================
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    extra = 0
    can_delete = True
    fields = (
        "user",
        "area",
        "puesto",
        "telefono_oficina",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class AxentraUserAdmin(BaseUserAdmin):
    """Administrador adaptado al esquema funcional por email."""

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    add_form = CustomUserCreationForm
    form = CustomUserChangeForm

    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_manager",
        "is_staff",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_manager",
        "is_staff",
        "is_superuser",
        "is_active",
        "is_deleted",
        "must_change_password",
        "is_email_verified",
        "created_at",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
        "phone",
    )

    ordering = ("-created_at",)
    inlines = (UserProfileInline,)
    filter_horizontal = ()
    readonly_fields = (
        "id",
        "last_login",
        "date_joined",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Credenciales de Identidad", {"fields": ("id", "email", "password")}),
        ("Información Personal", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Gobernanza y Privilegios",
            {"fields": ("is_manager", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (
            "Estado Operativo",
            {"fields": ("is_active", "is_deleted", "deleted_at", "must_change_password", "is_email_verified")},
        ),
        ("Trazabilidad", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            "Alta de Funcionario",
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password",
                    "first_name",
                    "last_name",
                    "phone",
                    "is_manager",
                    "is_staff",
                    "is_active",
                    "must_change_password",
                    "is_email_verified",
                ),
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            return self.add_form

        return super(BaseUserAdmin, self).get_form(request, obj, **kwargs)


@admin.register(UserProfile)
class UserProfileAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "puesto",
        "dependencia_resuelta",
        "sede_resuelta",
        "area",
        "is_active",
        "is_deleted",
        "updated_at",
    )

    list_filter = (
        "is_active",
        "is_deleted",
        "area__dependencia",
        "area__sede_fisica",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "puesto",
        "telefono_oficina",
        "area__nombre",
        "area__dependencia__nombre",
        "area__dependencia__codigo_presupuestal",
        "area__sede_fisica__nombre",
    )

    autocomplete_fields = ("user", "area")

    fields = (
        "id",
        "user",
        "area",
        "puesto",
        "telefono_oficina",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

    def dependencia_resuelta(self, obj):
        return obj.dependencia.nombre if obj.dependencia else "Sin dependencia"

    dependencia_resuelta.short_description = "Dependencia"

    def sede_resuelta(self, obj):
        return obj.sede.nombre if obj.sede else "Sin sede"

    sede_resuelta.short_description = "Sede"


# =========================================================================
# 🏛️ BLOQUE 2: TOPOLOGÍA GUBERNAMENTAL
# =========================================================================
class AreaOperativaInline(admin.TabularInline):
    """Permite ver y crear áreas operativas dentro de una dependencia."""

    model = AreaOperativa
    extra = 0

    fields = (
        "nombre",
        "sede_fisica",
        "slug",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = ("sede_fisica",)


@admin.register(Sede)
class SedeAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "nombre",
        "direccion",
        "encargado_sede",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "nombre",
        "direccion",
        "encargado_sede__email",
        "encargado_sede__first_name",
        "encargado_sede__last_name",
    )

    autocomplete_fields = ("encargado_sede",)

    fields = (
        "id",
        "nombre",
        "direccion",
        "encargado_sede",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields


@admin.register(Dependencia)
class DependenciaAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "codigo_presupuestal",
        "nombre",
        "slug",
        "parent",
        "encargado_departamento",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "is_active",
        "is_deleted",
        "parent",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "nombre",
        "codigo_presupuestal",
        "slug",
        "parent__nombre",
        "parent__codigo_presupuestal",
        "encargado_departamento__email",
        "encargado_departamento__first_name",
        "encargado_departamento__last_name",
    )

    autocomplete_fields = (
        "parent",
        "encargado_departamento",
    )

    fields = (
        "id",
        "nombre",
        "codigo_presupuestal",
        "slug",
        "parent",
        "encargado_departamento",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "id",
        "slug",
        "created_at",
        "updated_at",
    )

    inlines = (AreaOperativaInline,)


@admin.register(AreaOperativa)
class AreaOperativaAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "nombre",
        "dependencia",
        "codigo_dependencia",
        "sede_link",
        "slug",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "is_active",
        "is_deleted",
        "dependencia",
        "sede_fisica",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "nombre",
        "slug",
        "dependencia__nombre",
        "dependencia__codigo_presupuestal",
        "sede_fisica__nombre",
    )

    autocomplete_fields = (
        "dependencia",
        "sede_fisica",
    )

    fields = (
        "id",
        "nombre",
        "slug",
        "dependencia",
        "sede_fisica",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = (
        "id",
        "slug",
        "created_at",
        "updated_at",
    )

    def sede_link(self, obj):
        return obj.sede_fisica.nombre if obj.sede_fisica else "Sin sede"

    sede_link.short_description = "Sede Física"

    def codigo_dependencia(self, obj):
        return obj.dependencia.codigo_presupuestal if obj.dependencia else "-"

    codigo_dependencia.short_description = "Código DEP"


@admin.register(AppDependencyCapability)
class AppDependencyCapabilityAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "dependencia",
        "codigo_dependencia",
        "app",
        "can_operate",
        "can_supervise",
        "can_authorize",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "app",
        "can_operate",
        "can_supervise",
        "can_authorize",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "dependencia__nombre",
        "dependencia__codigo_presupuestal",
        "app__name",
        "app__slug",
    )

    autocomplete_fields = (
        "dependencia",
        "app",
    )

    fields = (
        "id",
        "app",
        "dependencia",
        "can_operate",
        "can_supervise",
        "can_authorize",
        "custom_settings",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

    def codigo_dependencia(self, obj):
        return obj.dependencia.codigo_presupuestal if obj.dependencia else "-"

    codigo_dependencia.short_description = "Código DEP"


# =========================================================================
# 🛡️ BLOQUE 3: MATRICES, PERÍMETROS Y SINGLETON CONFIG
# =========================================================================
@admin.register(AppModule)
class AppModuleAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "version",
        "module_kind",
        "health_status",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "module_kind",
        "health_status",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "slug",
        "description",
    )

    fields = (
        "id",
        "name",
        "slug",
        "description",
        "version",
        "icon",
        "entry_url_name",
        "module_kind",
        "dependencies",
        "optional_integrations",
        "health_status",
        "health_message",
        "last_health_check_at",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields + (
        "slug",
        "version",
        "icon",
        "entry_url_name",
        "module_kind",
        "dependencies",
        "optional_integrations",
        "health_status",
        "health_message",
        "last_health_check_at",
        "is_active",
    )


@admin.register(UserAppRole)
class UserAppRoleAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "user_email",
        "app_name",
        "role",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "role",
        "is_active",
        "is_deleted",
        "app",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "app__name",
        "app__slug",
    )

    autocomplete_fields = (
        "user",
        "app",
    )

    fields = (
        "id",
        "user",
        "app",
        "role",
        "permissions_list",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

    def user_email(self, obj):
        return obj.user.email if obj.user else "Sin usuario"

    user_email.short_description = "Funcionario"

    def app_name(self, obj):
        return obj.app.name if obj.app else "Sin módulo"

    app_name.short_description = "Módulo"


@admin.register(Municipality)
class MunicipalityAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "state_code",
        "state_name",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "state_code",
        "state_name",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "code",
        "name",
        "state_code",
        "state_name",
    )

    fields = (
        "id",
        "code",
        "name",
        "state_code",
        "state_name",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

@admin.register(OfficialParameter)
class OfficialParameterAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "parameter_type",
        "year",
        "name",
        "code",
        "display_value",
        "unit",
        "valid_from",
        "valid_to",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "parameter_type",
        "year",
        "unit",
        "is_active",
        "is_deleted",
        "valid_from",
        "valid_to",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "code",
        "parameter_type",
        "source",
        "notes",
    )

    fields = (
        "id",
        "parameter_type",
        "year",
        "name",
        "code",
        "value",
        "unit",
        "valid_from",
        "valid_to",
        "source",
        "notes",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

    ordering = (
        "-year",
        "parameter_type",
        "name",
    )

@admin.register(TenantConfig)
class TenantConfigAdmin(AxentraBaseAdminMixin, admin.ModelAdmin):
    list_display = (
        "entidad_nombre",
        "siglas",
        "municipality",
        "municipality_code",
        "app_name",
        "rfc",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    list_filter = (
        "municipality",
        "is_active",
        "is_deleted",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "app_name",
        "entidad_nombre",
        "siglas",
        "rfc",
        "direccion_oficial",
        "municipality__code",
        "municipality__name",
    )

    autocomplete_fields = (
        "municipality",
    )

    fields = (
        "id",
        "app_name",
        "entidad_nombre",
        "siglas",
        "municipality",
        "direccion_oficial",
        "rfc",
        "logo_light",
        "logo_dark",
        "primary_color_class",
        "primary_color",
        "secondary_color",
        "accent_color",
        "enable_whatsapp_support",
        "whatsapp_number",
        "is_active",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    )

    readonly_fields = AxentraBaseAdminMixin.readonly_fields

    def municipality_code(self, obj):
        return obj.municipality.code if obj.municipality else "-"

    municipality_code.short_description = "Clave MUN"


# =========================================================================
# 🛰️ BLOQUE 4: BITÁCORA FORENSE E HISTORIAL INMUTABLE
# =========================================================================
@admin.register(SecurityAuditLog)
class SecurityAuditLogAdmin(admin.ModelAdmin):
    """Caja negra forense inmutable."""

    list_display = (
        "created_at",
        "level_status",
        "app_namespace",
        "action_type",
        "module_component",
        "operator_email",
        "target_email",
        "action_name",
        "search_target",
        "ip_address",
    )

    list_filter = (
        "app_namespace",
        "action_type",
        "module_component",
        "level_status",
        "created_at",
    )

    search_fields = (
        "operator_user__email",
        "target_user__email",
        "action_type",
        "module_component",
        "action_name",
        "search_target",
        "target_scope",
        "ip_address",
    )

    ordering = ("-created_at",)

    fields = (
        "id",
        "created_at",
        "level_status",
        "app_namespace",
        "action_type",
        "module_component",
        "operator_user",
        "target_user",
        "action_name",
        "search_target",
        "target_scope",
        "ip_address",
        "user_agent",
        "payload_json",
    )

    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False

    def operator_email(self, obj):
        return obj.operator_user.email if obj.operator_user else "SISTEMA"

    operator_email.short_description = "Operador"

    def target_email(self, obj):
        return obj.target_user.email if obj.target_user else "GLOBAL / SISTEMA"

    target_email.short_description = "Funcionario Destino"
    


# Excepciones de alcance: solo superusuarios vigentes; Django Admin registra cambios.
from apps.security.models import DepartmentAccessGrant


@admin.register(DepartmentAccessGrant)
class DepartmentAccessGrantAdmin(admin.ModelAdmin):
    list_display = ('membership', 'source_department', 'target_department', 'permission', 'is_active', 'expires_at')
    list_filter = ('is_active', 'permission')
    raw_id_fields = ('membership', 'source_department', 'target_department')
    readonly_fields = ('granted_by', 'created_at', 'updated_at')

    def _can_manage(self, request):
        return request.user.is_active and not request.user.is_deleted and request.user.is_superuser

    def has_module_permission(self, request):
        return self._can_manage(request)

    def has_view_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_add_permission(self, request):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_delete_permission(self, request, obj=None):
        return False  # Revocar con is_active=False; conservar el registro.

    def save_model(self, request, obj, form, change):
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)

# Las claves OTP se gestionan exclusivamente con prueba de contraseña y segundo
# factor en las vistas propias; no exponer secretos/códigos mediante Admin.
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice
for device_model in (TOTPDevice, StaticDevice):
    if admin.site.is_registered(device_model):
        admin.site.unregister(device_model)
