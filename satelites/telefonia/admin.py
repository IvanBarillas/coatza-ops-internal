from django.contrib import admin

from .models import Evidencia, Linea, Movimiento, Reporte


@admin.register(Linea)
class LineaAdmin(admin.ModelAdmin):
    list_display = ("identificador", "sitio", "tipo", "velocidad", "is_active")
    search_fields = ("identificador", "sitio")
    list_filter = ("tipo", "is_active")


@admin.register(Reporte)
class ReporteAdmin(admin.ModelAdmin):
    list_display = ("folio", "linea_texto", "sitio_texto", "estatus", "levantado", "atendido")
    list_filter = ("estatus",)
    search_fields = ("folio", "linea_texto", "sitio_texto")

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Movimiento)
admin.site.register(Evidencia)
