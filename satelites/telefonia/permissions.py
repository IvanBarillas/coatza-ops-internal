class TelefoniaPermissions:
    APP_CODE = "telefonia"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Telefonía y enlaces.",
        "can_view_reports": "Permite consultar los reportes a Telmex, las líneas y el mapa.",
        "can_create_report": "Permite registrar reportes de falla (con el folio de Telmex).",
        "can_update_report": "Permite comentar, subir evidencia, marcar atendido, reasignar y corregir cualquier reporte.",
        "can_cancel_report": "Permite cancelar (con motivo) o reabrir reportes.",
        "can_manage_lines": "Permite dar de alta y editar líneas y enlaces, con su ubicación.",
        "can_view_own_reports": "Permite ver los reportes asignados al usuario (Mis pendientes).",
        "can_update_own_report": "Permite comentar, subir evidencia y marcar atendidos los reportes asignados al usuario.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_view_reports", "can_create_report", "can_update_report", "can_cancel_report",
            "can_manage_lines", "can_view_own_reports", "can_update_own_report",
        ],
        "operador": [
            "has_access_module", "can_view_reports", "can_create_report", "can_update_report", "can_manage_lines",
            "can_view_own_reports", "can_update_own_report",
        ],
        "tecnico": ["has_access_module", "can_view_own_reports", "can_update_own_report"],
        "viewer": ["has_access_module", "can_view_reports"],
    }

    ROLE_WEIGHTS = {"owner": 100, "operador": 60, "tecnico": 30, "viewer": 20}

    SIDEBAR_MENU = [
        ["phone-call", "Reportes", "telefonia:reportes", 1, "can_view_reports"],
        ["clipboard-list", "Mis pendientes", "telefonia:mis_pendientes", 2, "can_view_own_reports"],
        ["plus-circle", "Nuevo reporte", "telefonia:reporte_crear", 3, "can_create_report"],
        ["map", "Mapa", "telefonia:mapa", 4, "can_view_reports"],
        ["radio-tower", "Líneas", "telefonia:lineas", 5, "can_view_reports"],
    ]
