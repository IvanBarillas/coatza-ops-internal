class SeguimientosOficiosPermissions:
    APP_CODE = "seguimientos_oficios"

    PERMISSIONS = {
        "has_access_module": "Permite ingresar al módulo de Seguimiento de Oficios.",
        "can_view_oficios": "Permite consultar los documentos de su dirección.",
        "can_create_oficio": "Permite registrar documentos nuevos.",
        "can_update_status": "Permite marcar un documento como entregado.",
        "can_upload_files": "Permite adjuntar PDF (original o evidencia) a un documento.",
        "can_manage_catalogs": "Permite crear y editar direcciones y sus nomenclaturas de folio.",
        "can_edit_oficio": "Permite corregir datos de un documento (asunto, remitente o destinatario, fecha), con rastro en el historial.",
        "can_view_tracking": "Permite ver el seguimiento (semáforo) de los oficios enviados pendientes de entregar o de subir evidencia.",
        "can_remove_files": "Permite quitar archivos adjuntados por error (queda registrado con motivo).",
        "can_cancel_oficio": "Permite cancelar documentos (con motivo) que no estén concluidos.",
        "can_cancel_concluded": "Permiso especial: permite cancelar documentos ya concluidos, con motivo.",
    }

    ROLE_MAPPING = {
        "owner": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio", "can_cancel_concluded",
            "can_manage_catalogs", "can_view_tracking", "can_remove_files",
        ],
        "editor": [
            "has_access_module", "can_view_oficios", "can_create_oficio",
            "can_update_status", "can_upload_files", "can_edit_oficio", "can_cancel_oficio",
            "can_view_tracking", "can_remove_files",
        ],
        "viewer": ["has_access_module", "can_view_oficios", "can_view_tracking"],
        "seguimiento": ["has_access_module", "can_view_tracking"],
    }

    ROLE_WEIGHTS = {"owner": 100, "editor": 60, "viewer": 20, "seguimiento": 10}

    SIDEBAR_MENU = [
        ["file-text", "Documentos", "seguimientos_oficios:documento_list", 1, "can_view_oficios"],
        ["search", "Búsqueda", "seguimientos_oficios:busqueda", 2, "can_view_oficios"],
        ["activity", "Seguimiento", "seguimientos_oficios:seguimiento", 3, "can_view_tracking"],
        ["plus-circle", "Registrar documento", "seguimientos_oficios:documento_create", 4, "can_create_oficio"],
        ["layers", "Catálogos", "seguimientos_oficios:catalogos", 6, "can_manage_catalogs"],
    ]
