class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Seguimiento de Oficios.",
        "can_view_oficios": "Permite consultar los documentos de su dirección.",
        "can_create_oficio": "Permite registrar documentos nuevos.",
        "can_update_status": "Permite marcar un documento como entregado.",
        "can_cancel_oficio": "Permite cancelar documentos (con motivo) que no estén concluidos.",
        "can_cancel_concluded": "Permiso especial: permite cancelar documentos ya concluidos, con motivo.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_cancel_oficio", "can_cancel_concluded",
        ],
        "editor": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_cancel_oficio",
        ],
        "viewer": ["has_access_module", "can_view_oficios"],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20}

    SIDEBAR_MENU = [
        ["file-text", "Documentos", "seguimientos_oficios:documento_list", 1, "can_view_oficios"],
        ["plus-circle", "Registrar documento", "seguimientos_oficios:documento_create", 2, "can_create_oficio"],
    ]
