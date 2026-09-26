class EventosPermissions:
    APP_CODE = "eventos"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Eventos.",
        "can_view_own": "Permite ver los eventos en los que está asignado.",
        "can_view_calendar": "Permite ver el calendario de eventos y la carga de cada técnico.",
        "can_view_all_events": "Permite consultar la lista y el detalle de todos los eventos.",
        "can_add_notes": "Permite agregar notas de seguimiento a un evento.",
        "can_manage_events": "Permite crear y editar eventos, asignar técnicos, vincular vales, llevar los trámites de telefonía y cambiar el estado.",
    }

    ROLE_MAPPING = {
        "owner": ["has_access_module", "can_view_own", "can_view_calendar", "can_view_all_events", "can_add_notes", "can_manage_events"],
        "coordinador": ["has_access_module", "can_view_own", "can_view_calendar", "can_view_all_events", "can_add_notes", "can_manage_events"],
        "tecnico": ["has_access_module", "can_view_own", "can_view_calendar", "can_view_all_events", "can_add_notes"],
        "viewer": ["has_access_module", "can_view_calendar", "can_view_all_events"],
    }

    ROLE_WEIGHTS = {"owner": 100, "coordinador": 70, "tecnico": 30, "viewer": 10}

    SIDEBAR_MENU = [
        ["calendar-check", "Mis eventos", "eventos:mis_eventos", 1, "can_view_own"],
        ["calendar-days", "Calendario", "eventos:calendario", 2, "can_view_calendar"],
        ["list-checks", "Eventos", "eventos:eventos", 3, "can_view_all_events"],
        ["calendar-plus", "Nuevo evento", "eventos:evento_crear", 4, "can_manage_events"],
    ]
