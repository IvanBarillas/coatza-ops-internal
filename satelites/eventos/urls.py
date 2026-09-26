from django.urls import path

from . import views

app_name = "eventos"

urlpatterns = [
    path("", views.inicio_view, name="inicio"),
    path("mis-eventos/", views.mis_eventos_view, name="mis_eventos"),
    path("calendario/", views.calendario_view, name="calendario"),
    path("eventos/", views.eventos_view, name="eventos"),
    path("eventos/nuevo/", views.evento_form_view, name="evento_crear"),
    path("eventos/<uuid:pk>/", views.evento_detalle_view, name="evento_detalle"),
    path("eventos/<uuid:pk>/editar/", views.evento_form_view, name="evento_editar"),
]
