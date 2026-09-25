from django.urls import path

from . import views

app_name = "seguimientos_oficios"

urlpatterns = [
    path("", views.documento_list_view, name="documento_list"),
    path("buscar/", views.busqueda_view, name="busqueda"),
    path("<uuid:pk>/visor/<uuid:adjunto_pk>/", views.visor_view, name="visor"),
    path("mis-pendientes/", views.mis_pendientes_view, name="mis_pendientes"),
    path("nuevo/", views.documento_create_view, name="documento_create"),
    path("catalogos/", views.catalogos_view, name="catalogos"),
    path("catalogos/direcciones/nueva/", views.direccion_editar_view, name="direccion_crear"),
    path("catalogos/direcciones/<uuid:pk>/", views.direccion_editar_view, name="direccion_editar"),
    path("catalogos/direcciones/<uuid:pk>/nomenclaturas/", views.nomenclatura_crear_view, name="nomenclatura_crear"),
    path("catalogos/direcciones/<uuid:pk>/gestores/", views.gestor_crear_view, name="gestor_crear"),
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
