from django.urls import path

from . import views

app_name = "permisos_personal"

urlpatterns = [
    path("", views.inicio_view, name="inicio"),
    path("mis-permisos/", views.mis_solicitudes_view, name="mis_solicitudes"),
    path("solicitar/", views.solicitud_crear_view, name="solicitud_crear"),
    path("solicitudes/<uuid:pk>/cancelar/", views.solicitud_cancelar_view, name="solicitud_cancelar"),
    path("solicitudes/<uuid:pk>/validar/", views.solicitud_validar_view, name="solicitud_validar"),
    path("solicitudes/", views.solicitudes_view, name="solicitudes"),
    path("solicitudes/exportar/", views.solicitudes_exportar_view, name="solicitudes_exportar"),
    path("calendario/", views.calendario_view, name="calendario"),
    path("calendario/exportar/", views.calendario_exportar_view, name="calendario_exportar"),
    path("empleados/", views.empleados_view, name="empleados"),
    path("empleados/nuevo/", views.empleado_form_view, name="empleado_crear"),
    path("empleados/<uuid:pk>/", views.empleado_detalle_view, name="empleado_detalle"),
    path("empleados/<uuid:pk>/editar/", views.empleado_form_view, name="empleado_editar"),
    path("configuracion/", views.configuracion_view, name="configuracion"),
]
