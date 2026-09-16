# apps/security/urls/security_urls.py

from django.urls import path

from apps.security.views.security_views import (
    add_capability_node_view,
    descargar_auditoria_excel_view,
    dynamic_permission_matrix_view,
    expulsar_usuario_modulo_total_ajax_view,
    guardar_llaves_json_view,
    inyectar_funcionario_view,
    matrix_capabilities_view,
    privacidad_cookies_view,
    security_control_panel_view,
    security_applications_view,
    security_dashboard_view,
    security_global_matrix_forensic_view,
    tenant_config_view,
    toggle_capability_ajax_view,
    toggle_user_modulo_active_ajax_view,
)

# El namespace 'security' se amarra en el archivo raíz principal del proyecto
urls_security = [
    # 🏁 PILAR 1: Panel Administrativo / Cockpit Security
    path("applications/", security_applications_view, name="applications"),
    path("control/", security_control_panel_view, name="control_panel"),

    # 📊 PILAR 2: Consola Analítica Forense / Packet Stream
    path("dashboard/", security_dashboard_view, name="dashboard"),
    path("dashboard/analytics/download/excel/", descargar_auditoria_excel_view, name="descargar_auditoria_excel"),

    # 🪐 PILAR 3: Matriz Dinámica de Permisos
    path("matriz/", dynamic_permission_matrix_view, name="dynamic_matrix"),
    path("matriz/auditoria-global/", security_global_matrix_forensic_view, name="global_matrix_forensic"),
    path("matriz/guardar-llaves/<uuid:app_id>/<uuid:user_id>/", guardar_llaves_json_view, name="guardar_llaves"),
    path("matriz/inyectar-funcionario/<uuid:app_id>/", inyectar_funcionario_view, name="inyectar_funcionario"),
    path("matriz/toggle-status/<uuid:user_id>/<uuid:app_id>/", toggle_user_modulo_active_ajax_view, name="toggle_user_modulo_active"),
    path("matriz/purga-total/<uuid:user_id>/<uuid:app_id>/", expulsar_usuario_modulo_total_ajax_view, name="expulsar_usuario_modulo_total"),

    # 🎛️ PILAR 4: Gobernanza de Capacidades Geográficas
    path("platform/capabilities/", matrix_capabilities_view, name="matrix_capabilities"),
    path("platform/capabilities/add/<uuid:app_id>/", add_capability_node_view, name="add_capability_node"),

    # 🔄 PILAR 5: Endpoint Interceptor Asíncrono para Interruptores en Vivo
    path("platform/capabilities/toggle/<uuid:dep_id>/<uuid:app_id>/", toggle_capability_ajax_view, name="toggle_capability"),

    # ⚙️ PILAR 6: Configuración Corporativa Global / Tenant Config
    path("identidad/", tenant_config_view, name="tenant_config"),
    path("identidad/privacidad-cookies/", privacidad_cookies_view, name="privacidad_cookies"),
]