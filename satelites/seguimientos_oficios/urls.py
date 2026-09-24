from django.urls import path

from . import views

app_name = "seguimientos_oficios"

urlpatterns = [
    path("", views.documento_list_view, name="documento_list"),
    path("nuevo/", views.documento_create_view, name="documento_create"),
    path("<uuid:pk>/", views.documento_detail_view, name="documento_detail"),
    path("<uuid:pk>/entregar/", views.documento_entregar_view, name="documento_entregar"),
    path("<uuid:pk>/adjuntar/", views.documento_adjuntar_view, name="documento_adjuntar"),
    path("<uuid:pk>/adjuntos/<uuid:adjunto_pk>/", views.adjunto_descargar_view, name="adjunto_descargar"),
    path("<uuid:pk>/cancelar/", views.documento_cancelar_view, name="documento_cancelar"),
]
