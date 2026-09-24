from django.contrib import admin

from .models import Direccion, Documento, HistorialDocumento, Nomenclatura


@admin.register(Nomenclatura)
class NomenclaturaAdmin(admin.ModelAdmin):
    list_display = ("direccion", "clase", "plantilla", "is_active")
    list_filter = ("direccion", "clase")


admin.site.register(Direccion)


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("folio", "sentido", "clase", "estado", "direccion_nombre", "asunto", "fecha")
    list_filter = ("sentido", "clase", "estado")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistorialDocumento)
class HistorialAdmin(admin.ModelAdmin):
    list_display = ("documento", "accion", "usuario_nombre", "created_at")
    readonly_fields = [f.name for f in HistorialDocumento._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
