class PermisosPersonalPermissions:
    APP_CODE = "permisos_personal"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Permisos del personal.",
        "can_request_own": "Permite solicitar, consultar y cancelar sus propias vacaciones y días económicos.",
        "can_view_calendar": "Permite ver el calendario de ausencias y la cobertura por sede.",
        "can_view_all_requests": "Permite consultar las solicitudes de todo el personal.",
        "can_validate_requests": "Permite marcar las solicitudes como validadas (y cancelar cualquiera, con motivo).",
        "can_manage_employees": "Permite dar de alta empleados y ajustar sus días por periodo.",
        "can_manage_config": "Permite definir los días económicos, la tabla de vacaciones por antigüedad y el mínimo por sede.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_request_own", "can_view_calendar", "can_view_all_requests", "can_validate_requests",
            "can_manage_employees", "can_manage_config",
        ],
        "control": [
            "has_access_module", "can_request_own", "can_view_calendar", "can_view_all_requests", "can_validate_requests",
            "can_manage_employees", "can_manage_config",
        ],
        "empleado": ["has_access_module", "can_request_own", "can_view_calendar"],
        "viewer": ["has_access_module", "can_view_calendar", "can_view_all_requests"],
    }

    ROLE_WEIGHTS = {"owner": 100, "control": 70, "empleado": 20, "viewer": 10}

    SIDEBAR_MENU = [
        ["calendar-check", "Mis permisos", "permisos_personal:mis_solicitudes", 1, "can_request_own"],
        ["calendar-plus", "Nueva solicitud", "permisos_personal:solicitud_crear", 2, "can_request_own"],
        ["calendar-days", "Calendario", "permisos_personal:calendario", 3, "can_view_calendar"],
        ["clipboard-check", "Solicitudes", "permisos_personal:solicitudes", 4, "can_view_all_requests"],
        ["users", "Empleados", "permisos_personal:empleados", 5, "can_manage_employees"],
        ["settings-2", "Configuración", "permisos_personal:configuracion", 6, "can_manage_config"],
    ]
