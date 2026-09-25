from django.urls import path

from . import views

app_name = "telefonia"

urlpatterns = [
    path("", views.inicio_view, name="inicio"),
    path("reportes/", views.reportes_view, name="reportes"),
    path("reportes/nuevo/", views.reporte_crear_view, name="reporte_crear"),
    path("pendientes/", views.mis_pendientes_view, name="mis_pendientes"),
    path("reportes/<uuid:pk>/", views.reporte_detalle_view, name="reporte_detalle"),
    path("reportes/<uuid:pk>/editar/", views.reporte_editar_view, name="reporte_editar"),
    path("reportes/<uuid:pk>/comentar/", views.reporte_comentar_view, name="reporte_comentar"),
    path("reportes/<uuid:pk>/evidencia/", views.reporte_evidencia_view, name="reporte_evidencia"),
    path("reportes/<uuid:pk>/evidencia/<uuid:evidencia_pk>/", views.evidencia_descargar_view, name="evidencia_descargar"),
    path("reportes/<uuid:pk>/atender/", views.reporte_atender_view, name="reporte_atender"),
    path("reportes/<uuid:pk>/cancelar/", views.reporte_cancelar_view, name="reporte_cancelar"),
    path("reportes/<uuid:pk>/reabrir/", views.reporte_reabrir_view, name="reporte_reabrir"),
    path("reportes/<uuid:pk>/asignar/", views.reporte_asignar_view, name="reporte_asignar"),
    path("lineas/", views.lineas_view, name="lineas"),
    path("lineas/nueva/", views.linea_form_view, name="linea_crear"),
    path("lineas/<uuid:pk>/", views.linea_detalle_view, name="linea_detalle"),
    path("lineas/<uuid:pk>/editar/", views.linea_form_view, name="linea_editar"),
    path("mapa/", views.mapa_view, name="mapa"),
]
