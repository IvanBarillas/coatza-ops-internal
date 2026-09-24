class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Seguimiento de Oficios.",
        "can_view_oficios": "Permite consultar los oficios de su dirección.",
        "can_create_oficio": "Permite registrar oficios nuevos.",
    }

    ROLE_MAPPING = {
        "owner": ["has_access_module", "can_view_oficios", "can_create_oficio"],
        "editor": ["has_access_module", "can_view_oficios", "can_create_oficio"],
        "viewer": ["has_access_module", "can_view_oficios"],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20}

    SIDEBAR_MENU = [
        ["file-text", "Oficios", "seguimientos_oficios:documento_list", 1, "can_view_oficios"],
        ["plus-circle", "Registrar oficio", "seguimientos_oficios:documento_create", 2, "can_create_oficio"],
    ]
