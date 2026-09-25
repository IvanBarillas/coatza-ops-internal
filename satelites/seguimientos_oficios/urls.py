from django.urls import path

from . import views
from .prestamos import views as prestamos_views
from .soporte import views as soporte_views

app_name = "seguimientos_oficios"

urlpatterns = [
    path("documentos/", views.documento_list_view, name="documento_list"),
    path("buscar/", views.busqueda_view, name="busqueda"),
    path("prestamos/", prestamos_views.prestamos_view, name="prestamos"),
    path("prestamos/vales/", prestamos_views.vales_view, name="vales"),
    path("prestamos/nuevo/", prestamos_views.vale_crear_view, name="vale_crear"),
    path("prestamos/<uuid:pk>/imprimir/", prestamos_views.vale_imprimir_view, name="vale_imprimir"),
    path("prestamos/<uuid:pk>/editar/", prestamos_views.vale_editar_view, name="vale_editar"),
    path("prestamos/<uuid:pk>/devolucion/", prestamos_views.devolucion_view, name="vale_devolucion"),
    path("soporte/", soporte_views.soporte_view, name="soporte"),
    path("soporte/diagnostico/nuevo/", soporte_views.crear_diagnostico_view, name="soporte_crear_diagnostico"),
    path("soporte/baja/nueva/", soporte_views.crear_baja_view, name="soporte_crear_baja"),
    path("soporte/alta/nueva/", soporte_views.crear_alta_view, name="soporte_crear_alta"),
    path("soporte/<uuid:pk>/editar/", soporte_views.editar_view, name="soporte_editar"),
    path("soporte/<uuid:pk>/imprimir/", soporte_views.imprimir_view, name="soporte_imprimir"),
    path("bienes/", prestamos_views.bienes_view, name="bienes"),
    path("bienes/nuevo/", prestamos_views.bien_form_view, name="bien_crear"),
    path("bienes/<uuid:pk>/", prestamos_views.bien_detalle_view, name="bien_detalle"),
    path("bienes/<uuid:pk>/editar/", prestamos_views.bien_form_view, name="bien_editar"),
    path("<uuid:pk>/visor/<uuid:adjunto_pk>/", views.visor_view, name="visor"),
    path("<uuid:pk>/lector/<uuid:adjunto_pk>/", views.lector_pdf_view, name="lector"),
    path("", views.inicio_view, name="inicio"),
    path("seguimiento/", views.seguimiento_view, name="seguimiento"),
    path("gestor/", views.gestor_view, name="gestor"),
    path("gestor/<uuid:pk>/entrega/", views.gestor_entrega_view, name="gestor_entrega"),
    path("nuevo/", views.documento_create_view, name="documento_create"),
    path("catalogos/", views.catalogos_view, name="catalogos"),
    path("catalogos/direcciones/nueva/", views.direccion_editar_view, name="direccion_crear"),
    path("catalogos/direcciones/<uuid:pk>/", views.direccion_editar_view, name="direccion_editar"),
    path("catalogos/direcciones/<uuid:pk>/nomenclaturas/", views.nomenclatura_crear_view, name="nomenclatura_crear"),
    path("catalogos/direcciones/<uuid:pk>/gestores/", views.gestor_crear_view, name="gestor_crear"),
    path("catalogos/direcciones/<uuid:pk>/categorias/", views.categoria_crear_view, name="categoria_crear"),
    path("catalogos/direcciones/<uuid:pk>/categorias-bienes/", views.categoria_bien_crear_view, name="categoria_bien_crear"),
    path("catalogos/categorias-bienes/<uuid:pk>/", views.categoria_bien_actualizar_view, name="categoria_bien_actualizar"),
    path("catalogos/categorias/<uuid:pk>/", views.categoria_actualizar_view, name="categoria_actualizar"),
    path("catalogos/gestores/<uuid:pk>/", views.gestor_actualizar_view, name="gestor_actualizar"),
    path("catalogos/nomenclaturas/<uuid:pk>/", views.nomenclatura_actualizar_view, name="nomenclatura_actualizar"),
    path("<uuid:pk>/", views.documento_detail_view, name="documento_detail"),
    path("<uuid:pk>/editar/", views.documento_editar_view, name="documento_editar"),
    path("<uuid:pk>/entregar/", views.documento_entregar_view, name="documento_entregar"),
    path("<uuid:pk>/adjuntar/", views.documento_adjuntar_view, name="documento_adjuntar"),
    path("<uuid:pk>/adjuntos/<uuid:adjunto_pk>/quitar/", views.adjunto_quitar_view, name="adjunto_quitar"),
    path("<uuid:pk>/adjuntos/<uuid:adjunto_pk>/", views.adjunto_descargar_view, name="adjunto_descargar"),
    path("<uuid:pk>/cancelar/", views.documento_cancelar_view, name="documento_cancelar"),
]
