from django.urls import path

from . import views

app_name = "seguimientos_oficios"

urlpatterns = [
    path("", views.documento_list_view, name="documento_list"),
    path("nuevo/", views.documento_create_view, name="documento_create"),
    path("catalogos/", views.catalogos_view, name="catalogos"),
    path("catalogos/direcciones/nueva/", views.direccion_editar_view, name="direccion_crear"),
    path("catalogos/direcciones/<uuid:pk>/", views.direccion_editar_view, name="direccion_editar"),
    path("catalogos/direcciones/<uuid:pk>/nomenclaturas/", views.nomenclatura_crear_view, name="nomenclatura_crear"),
    path("catalogos/nomenclaturas/<uuid:pk>/", views.nomenclatura_actualizar_view, name="nomenclatura_actualizar"),
    path("configuracion/", views.configuracion_view, name="configuracion"),
    path("configuracion/<uuid:pk>/", views.configuracion_guardar_view, name="configuracion_guardar"),
    path("<uuid:pk>/bandeja/", views.documento_bandeja_view, name="documento_bandeja"),
    path("<uuid:pk>/bandeja/adjuntar/", views.documento_adjuntar_bandeja_view, name="documento_adjuntar_bandeja"),
    path("<uuid:pk>/", views.documento_detail_view, name="documento_detail"),
    path("<uuid:pk>/entregar/", views.documento_entregar_view, name="documento_entregar"),
    path("<uuid:pk>/adjuntar/", views.documento_adjuntar_view, name="documento_adjuntar"),
    path("<uuid:pk>/adjuntos/<uuid:adjunto_pk>/", views.adjunto_descargar_view, name="adjunto_descargar"),
    path("<uuid:pk>/cancelar/", views.documento_cancelar_view, name="documento_cancelar"),
]
